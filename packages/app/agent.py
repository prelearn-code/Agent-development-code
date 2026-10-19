"""Existing minimal Agent loop and interactive entry, moved into the application package."""

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
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
        "根据工具描述和参数结构生成 tool_calls。必填参数未提供时，仍保留该参数名，"
        '并将其值设为 JSON 空字符串 ""，客户端会检查并阻止不完整的调用。'
        "禁止用“待补充”“待提供”“未提供”“未知”、null 或编造的 ID 代替缺失参数。"
        '例如用户只提供 file_id="file_001" 时，签名工具参数应为 '
        '{"file_id":"file_001","key_id":""}。'
        "保留用户已经提供的参数，不要把已有值改为空字符串；未提供的可选参数可省略。"
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


def _to_result(
    call: ToolCall,
    result: dict[str, Any],
    duration_ms: float,
    provider_call_id: str | None = None,
) -> ToolResult[Any]:
    """把工具原始结果包成契约类型；success 以工具自己的 ok 字段为准。"""
    ok = result.get("ok") is True
    return ToolResult(
        success=ok,
        data=result if ok else None,
        error=None if ok else str(result.get("error", "tool_error")),
        metadata={
            "run_id": call.run_id,
            "call_id": call.call_id,
            "provider_call_id": provider_call_id,
            "tool_name": call.tool_name,
            "step_index": call.step_index,
            "duration_ms": round(duration_ms, 3),
            "started_at": datetime.now(UTC).isoformat(),
            "raw": result,
        },
    )


def _evidence(outcome: ToolResult[Any], result: dict[str, Any]) -> dict[str, Any]:
    """可审计的一条证据：谁、第几步、跑了什么、拿到什么、耗时多少。"""
    return {
        "run_id": outcome.metadata["run_id"],
        "call_id": outcome.metadata["call_id"],
        "provider_call_id": outcome.metadata["provider_call_id"],
        "tool_name": outcome.metadata["tool_name"],
        "step_index": outcome.metadata["step_index"],
        "ok": outcome.success,
        "error": outcome.error,
        "result": result,
        "duration_ms": outcome.metadata["duration_ms"],
        "started_at": outcome.metadata["started_at"],
    }


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
    for step in range(max_steps):
        assistant = await asyncio.to_thread(
            call_model, messages, tools=tools, model=model, base_url=base_url
        )
        messages.append(assistant)

        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            return cast(str, assistant.get("content", ""))

        for index, call in enumerate(tool_calls):
            function = call.get("function") or {}
            name = function.get("name", "")
            arguments = function.get("arguments", {})
            # 两个号分工不同：call_id 是应用自己的账本号；provider_call_id 是模型侧的
            # 回执号，只用于把 tool 消息绑回那次请求，不作为可信身份。
            provider_call_id = call.get("id")
            if not isinstance(provider_call_id, str) or not provider_call_id:
                provider_call_id = None
            tool_call = ToolCall(
                call_id=f"call_{step:02d}_{index}",
                tool_name=name,
                arguments=_as_arguments(arguments),
                step_index=step,
                run_id=run_id,
            )
            started = time.monotonic()
            result = await execute_tool(session, name, arguments, tools)
            outcome = _to_result(
                tool_call, result, (time.monotonic() - started) * 1000, provider_call_id
            )
            print(f"[工具]{name}({arguments}) -> {result}", file=sys.stderr)
            if evidence is not None:
                evidence.append(_evidence(outcome, result))

            messages.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    # 协议回执：优先回填 provider 的 id（严格后端会校验），没有才回落内部号。
                    "tool_call_id": provider_call_id or tool_call.call_id,
                    # 模型可见的字节保持不变，避免改动影响提示词效果。
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    raise RuntimeError(f"工具调用超过 {max_steps} 轮，已停止")


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
    return {"status": "completed", "run_id": run_id, "answer": answer, "evidence": evidence}


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
