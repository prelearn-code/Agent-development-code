"""Existing minimal Agent loop and interactive entry, moved into the application package."""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import uuid4

from mcp import ClientSession
from mcp_integration.client.connection import connect_tools
from tools.executor import execute_tool

from packages.core.config import get_settings
from packages.core.models import ToolCall, ToolResult
from packages.llm.client import call_model

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


class Phase(StrEnum):
    """Loop 的显式状态。合法的下一步见 _ALLOWED。"""

    REQUEST_MODEL = "request_model"  # 唯一的决策点：请求模型并决定下一步
    DISPATCH_TOOLS = "dispatch_tools"  # 执行 pending_calls，结果回传
    FINISH = "finish"  # 正常结束：模型不再提议工具
    STOPPED = "stopped"  # 预算/轮次耗尽：结束但不回答


# 转移表本身就是自检问题 4 的答案：只有 REQUEST_MODEL 能决定结束。
_ALLOWED: dict[Phase, frozenset[Phase]] = {
    Phase.REQUEST_MODEL: frozenset({Phase.FINISH, Phase.DISPATCH_TOOLS, Phase.STOPPED}),
    Phase.DISPATCH_TOOLS: frozenset({Phase.REQUEST_MODEL}),
    Phase.FINISH: frozenset(),
    Phase.STOPPED: frozenset(),
}


@dataclass
class LoopState:
    """一次 Run 的控制流数据。

    只放数据、不放回调和连接：05 段可以直接把它序列化进 agent_runs/agent_steps，
    06 段恢复时据此决定从哪个 Phase 继续。pending_calls 也是 04 段流式累积的落点。
    """

    run_id: str
    messages: list[dict[str, Any]]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    step_index: int = 0
    phase: Phase = Phase.REQUEST_MODEL
    pending_calls: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    stop_reason: str = ""


class LoopStopped(RuntimeError):
    """轮次/预算耗尽导致的停止；由 run() 转成 status=stopped 的结构化结果。"""

    def __init__(self, reason: str, steps: int) -> None:
        super().__init__(f"Loop 已停止（{reason}），共执行 {steps} 步")
        self.reason = reason
        self.steps = steps


def _enter(state: LoopState, next_phase: Phase) -> None:
    """唯一的转移入口：非法转移当场失败，而不是悄悄跑错分支。"""
    if next_phase not in _ALLOWED[state.phase]:
        raise RuntimeError(f"非法状态转移：{state.phase.value} -> {next_phase.value}")
    state.phase = next_phase


async def _request_model(
    state: LoopState,
    *,
    tools: list[dict[str, Any]],
    model: str,
    base_url: str,
    max_steps: int,
) -> None:
    """REQUEST_MODEL：检查轮次预算 → 请求模型 → 进入 FINISH / DISPATCH_TOOLS / STOPPED。

    04 段在这里加 deadline、四类错误分类；03 段不需要动这里。
    """
    if state.step_index >= max_steps:
        state.stop_reason = "max_steps"
        _enter(state, Phase.STOPPED)
        return

    assistant = await asyncio.to_thread(
        call_model, state.messages, tools=tools, model=model, base_url=base_url
    )
    state.messages.append(assistant)

    tool_calls = assistant.get("tool_calls") or []
    if not tool_calls:
        state.answer = cast(str, assistant.get("content", ""))
        _enter(state, Phase.FINISH)
        return

    state.pending_calls = list(tool_calls)
    _enter(state, Phase.DISPATCH_TOOLS)


async def _dispatch_tools(
    state: LoopState,
    *,
    session: ClientSession,
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
    session: ClientSession,
    tools: list[dict[str, Any]],
    model: str,
    base_url: str,
    max_steps: int = 5,
    evidence: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> str:
    # 一次 Agent 任务的身份；调用方没给就新建。多轮对话每轮是一个新的 run。
    run_id = run_id or uuid4().hex
    messages.append({"role": "user", "content": user_text})
    state = LoopState(
        run_id=run_id,
        messages=messages,
        evidence=evidence if evidence is not None else [],
    )

    # 显式循环：每轮进入哪个 Phase 由状态决定，结束只有 FINISH 和 STOPPED 两种。
    while True:
        if state.phase is Phase.REQUEST_MODEL:
            await _request_model(
                state, tools=tools, model=model, base_url=base_url, max_steps=max_steps
            )
        elif state.phase is Phase.DISPATCH_TOOLS:
            await _dispatch_tools(state, session=session, tools=tools)
        elif state.phase is Phase.FINISH:
            return state.answer
        else:  # Phase.STOPPED
            raise LoopStopped(state.stop_reason, state.step_index)


async def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    messages = [SYSTEM_PROMPT]
    print("Crypto Agent已经启动，输入exit退出。")

    async with connect_tools() as (session, tools):
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
                    messages,
                    user_text,
                    session=session,
                    tools=tools,
                    model=args.model,
                    base_url=args.base_url,
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
    messages = [SYSTEM_PROMPT.copy()]
    run_id = uuid4().hex
    evidence: list[dict[str, Any]] = []
    try:
        async with connect_tools() as (session, tools):
            answer = await chat_turn(
                messages,
                question,
                session=session,
                tools=tools,
                model=settings.CONTROLLER_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
                evidence=evidence,
                run_id=run_id,
            )
    except LoopStopped as exc:
        # 撞限不是崩溃：给出结构化停止原因，05 段可以直接落库。
        return {
            "status": "stopped",
            "reason": exc.reason,
            "steps": exc.steps,
            "run_id": run_id,
            "evidence": evidence,
        }
    return {"status": "completed", "run_id": run_id, "answer": answer, "evidence": evidence}


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
