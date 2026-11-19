"""Existing minimal Agent loop and interactive entry, moved into the application package."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from mcp import Client
from mcp_integration.client.connection import connect_tools
from tools.executor import execute_tool

from packages.core.config import get_settings
from packages.core.errors import LLMError
from packages.core.loop_state import LoopState, Phase
from packages.core.models import ToolCall, ToolResult
from packages.llm.client import ModelClient, call_model, create_model_client
from packages.llm.context import ContextMessage

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "你是一个密码执行 agent，只能使用已有工具。用户操作意图明确且有对应工具时，"
        "根据工具描述和参数结构生成 tool_calls。必填参数缺失时不要调用工具，"
        "直接用自然语言向用户询问缺少哪些参数。"
        "已提供的参数必须原样保留；未提供的可选参数可省略，但不要编造任何 ID 或占位值。"
        "收到 missing_arguments 时，用自然语言询问 missing 列出的参数，"
        "本回合不要重复调用缺参工具，等待用户下一条消息补充。"
        "收到 invalid_arguments 时，询问用户修正，不要重复发送同样的错误参数。"
        "结合完整对话历史理解追问和补充信息，参数完整后再正常调用工具。"
    ),
}

HISTORY_COMPACT = {
    "role": "system",
    "content": "",
}


def _as_arguments(arguments: Any) -> dict[str, Any]:
    """模型可能给对象，也可能给 JSON 字符串；ToolCall.arguments 只接受对象。"""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
    return arguments if isinstance(arguments, dict) else {}


def _evidence(outcome: ToolResult[Any]) -> dict[str, Any]:
    """可审计的一条证据：谁、第几步、跑了什么、拿到什么、耗时多少。

    ToolResult 现在由 executor 直接产出；这里只补上 run/call 维度的字段，
    模型可见的原始 dict 在 metadata["wire"] 里。
    """
    metadata = outcome.metadata
    return {
        "run_id": metadata.get("run_id"),
        "call_id": metadata.get("call_id"),
        "provider_call_id": metadata.get("provider_call_id"),
        "tool_name": metadata.get("tool_name"),
        "step_index": metadata.get("step_index"),
        "ok": outcome.success,
        "error": outcome.error,
        "result": metadata.get("wire", {}),
        "duration_ms": metadata.get("duration_ms"),
        "started_at": metadata.get("started_at"),
    }


# 转移表本身就是自检问题 4 的答案：只有 REQUEST_MODEL 能决定结束。
_ALLOWED: dict[Phase, frozenset[Phase]] = {
    Phase.REQUEST_MODEL: frozenset({Phase.FINISH, Phase.DISPATCH_TOOLS, Phase.STOPPED}),
    Phase.DISPATCH_TOOLS: frozenset({Phase.REQUEST_MODEL}),
    Phase.FINISH: frozenset(),
    Phase.STOPPED: frozenset(),
}


class LoopStopped(RuntimeError):
    """轮次/预算耗尽或模型请求失败导致的停止；由 run() 转成结构化结果。"""

    def __init__(self, reason: str, steps: int, detail: str = "") -> None:
        message = f"Loop 已停止（{reason}），共执行 {steps} 步"
        if detail:
            message = f"{message}：{detail}"
        super().__init__(message)
        self.reason = reason
        self.steps = steps
        self.detail = detail


def _enter(state: LoopState, next_phase: Phase) -> None:
    """唯一的转移入口：非法转移当场失败，而不是悄悄跑错分支。"""
    if next_phase not in _ALLOWED[state.phase]:
        raise RuntimeError(f"非法状态转移：{state.phase.value} -> {next_phase.value}")
    state.phase = next_phase


async def _request_model(
    context: ContextMessage | None,
    state: LoopState,
    *,
    tools: list[dict[str, Any]],
    model: str,
    base_url: str,
    max_steps: int,
    model_client: ModelClient | None = None,
) -> dict[str, int] | None:
    """REQUEST_MODEL：检查轮次预算 → 请求模型 → 进入 FINISH / DISPATCH_TOOLS / STOPPED。

    返回本次模型响应的 token 计数。
    """
    if state.step_index >= max_steps:
        state.stop_reason = "max_steps"
        _enter(state, Phase.STOPPED)
        return None
    try:
        turn_usage: dict[str, int] = {}
        assistant = await call_model(
            state.messages,
            tools=tools,
            model=model,
            base_url=base_url,
            client=model_client,
            context=context,
            usage=turn_usage,
        )
    except LLMError as exc:
        # 模型请求失败：不是"继续跑"，而是带着原因进入 STOPPED。
        state.stop_reason = exc.reason
        state.stop_detail = str(exc)
        _enter(state, Phase.STOPPED)
        return None

    state.messages.append(assistant)
    tool_calls = assistant.get("tool_calls") or []
    if not tool_calls:
        state.answer = cast(str, assistant.get("content", ""))
        _enter(state, Phase.FINISH)
    else:
        state.pending_calls = list(tool_calls)
        _enter(state, Phase.DISPATCH_TOOLS)
    return turn_usage or None


async def _dispatch_tools(
    state: LoopState,
    *,
    session: Client,
    tools: list[dict[str, Any]],
) -> None:
    """DISPATCH_TOOLS：逐个执行 pending_calls，回传后回到 REQUEST_MODEL。

    03 段授权在 execute_tool 内；拒绝记录与 04 段预算/超时/重复检测
    都挂在这里的循环前后，不需要再改整体结构。
    """
    for index, call in enumerate(state.pending_calls):
        function = call.get("function") or {}
        name = function.get("name", "")
        arguments = function.get("arguments", {})
        # 两个号分工不同：call_id 是应用自己的账本号；provider_call_id 是模型侧的
        # 回执号，只用于把 tool 消息绑回那次请求，不作为可信身份。
        provider_call_id = call.get("id")
        if not isinstance(provider_call_id, str) or not provider_call_id:
            provider_call_id = None
        tool_call = ToolCall(
            call_id=f"call_{state.step_index:02d}_{index}",
            tool_name=name,
            arguments=_as_arguments(arguments),
            step_index=state.step_index,
            run_id=state.run_id,
        )
        # started_at 在调用前记录；耗时由 executor 统一测量并写进 metadata。
        started_at = datetime.now(UTC).isoformat()
        outcome = await execute_tool(session, name, arguments, tools)
        outcome.metadata |= {
            "run_id": state.run_id,
            "call_id": tool_call.call_id,
            "provider_call_id": provider_call_id,
            "step_index": state.step_index,
            "started_at": started_at,
        }
        wire = outcome.metadata.get("wire", {})
        print(f"[工具]{name}({arguments}) -> {wire}", file=sys.stderr)
        state.evidence.append(_evidence(outcome))

        state.messages.append(
            {
                "role": "tool",
                "tool_name": name,
                # 协议回执：优先回填 provider 的 id（严格后端会校验），没有才回落内部号。
                "tool_call_id": provider_call_id or tool_call.call_id,
                # 模型可见的字节保持不变：仍然发工具原始 dict（wire），内部才用 ToolResult。
                "content": json.dumps(wire, ensure_ascii=False),
            }
        )

    state.pending_calls = []
    state.step_index += 1
    _enter(state, Phase.REQUEST_MODEL)


async def chat_turn(
    messages: list[dict[str, Any]],
    user_text: str,
    *,
    session: Client,
    tools: list[dict[str, Any]],
    model: str,
    base_url: str,
    max_steps: int = 5,
    evidence: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    model_client: ModelClient | None = None,
    context: ContextMessage | None = None,
) -> str:
    """跑一轮对话。

    `messages` 是当前轮的消息容器（调用方传空列表即可），本轮状态会在结束时
    以快照追加进 `context.history`；`context` 提供 system / 历史摘要 / 历史轮次。
    """
    # 一次 Agent 任务的身份；调用方没给就新建。多轮对话每轮是一个新的 run。
    run_id = run_id or uuid4().hex
    messages.append({"role": "user", "content": user_text})
    state = LoopState(
        run_id=run_id,
        messages=messages,
        evidence=evidence if evidence is not None else [],
    )

    try:
        # 显式循环：每轮进入哪个 Phase 由状态决定，结束只有 FINISH 和 STOPPED 两种。
        while True:
            if state.phase is Phase.REQUEST_MODEL:
                turn_usage = await _request_model(
                    context,
                    state,
                    tools=tools,
                    model=model,
                    base_url=base_url,
                    max_steps=max_steps,
                    model_client=model_client,
                )
                if turn_usage is not None:
                    tokens = turn_usage["prompt_tokens"] + turn_usage["completion_tokens"]
                    previous_tokens = context.usage if context is not None else state.usage
                    state.usage += tokens - previous_tokens
                    if context is not None:
                        context.usage = tokens
            elif state.phase is Phase.DISPATCH_TOOLS:
                await _dispatch_tools(state, session=session, tools=tools)
            elif state.phase is Phase.FINISH:
                return state.answer
            else:  # Phase.STOPPED
                raise LoopStopped(state.stop_reason, state.step_index, state.stop_detail)
    finally:
        # 正常结束、预算停止、模型失败都要进历史：失败那几步同样需要审计。
        if context is not None:
            context.add_turn(state)


async def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    context = ContextMessage(
        system_message=SYSTEM_PROMPT.copy(),
        history_compact=[HISTORY_COMPACT],
    )

    print("Crypto Agent已经启动，输入exit退出。")

    async with create_model_client() as model_client, connect_tools() as (session, tools):
        context.tool_scheme = tools
        while True:
            try:
                user_text = (await asyncio.to_thread(input, "\n你> ")).strip()
            except EOFError:
                print()
                break

            if user_text.lower() in {"/exit", "/quit"}:
                break
            if not user_text:
                continue
            try:
                answer = await chat_turn(
                    [],
                    user_text,
                    session=session,
                    tools=context.tool_scheme,
                    model=args.model,
                    base_url=args.base_url,
                    model_client=model_client,
                    context=context,
                )
                print(f"助手<{answer}")
            except RuntimeError as exc:
                print(f"错误>{exc}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """CLI 默认值来自 Settings，命令行参数仍可临时覆盖（只影响本次运行）。"""
    settings = get_settings()
    parser = argparse.ArgumentParser(description="CryptoAgentdemo")
    parser.add_argument("--model", default=settings.CONTROLLER_MODEL)
    parser.add_argument("--base-url", default=settings.OLLAMA_BASE_URL)
    return parser


async def run(*, question: str) -> dict[str, object]:
    """Run the existing single-turn loop through the application's JSON CLI."""
    settings = get_settings()
    context = ContextMessage(system_message=SYSTEM_PROMPT.copy())
    messages: list[dict[str, Any]] = []
    run_id = uuid4().hex
    evidence: list[dict[str, Any]] = []
    async with create_model_client() as model_client, connect_tools() as (session, tools):
        try:
            answer = await chat_turn(
                messages,
                question,
                session=session,
                tools=tools,
                model=settings.CONTROLLER_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                evidence=evidence,
                run_id=run_id,
                model_client=model_client,
                context=context,
            )
        except LoopStopped as exc:
            # 必须在 async with 内部捕获：MCP 的 TaskGroup 会把逃逸异常包成
            # ExceptionGroup，外面的 except 就接不到了。
            failed = exc.reason.startswith("llm_")
            result: dict[str, object] = {
                "status": "failed" if failed else "stopped",
                "reason": exc.reason,
                "detail": exc.detail,
                "steps": exc.steps,
            }
        else:
            result = {"status": "completed", "answer": answer}
    return {
        **result,
        "run_id": run_id,
        "usage": {
            "run_tokens": context.history[-1].usage,
            "context_tokens": context.usage,
        },
        "evidence": evidence,
    }


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
