"""显式状态机：结束条件、转移顺序与预算停止。"""

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult
from packages.app import agent
from packages.core.config import Settings
from packages.llm.context import ContextMessage

DIGEST = "88036eecf53de118265ae2c33ec3881e8d98cf3a29507fea6c9802ae4e1f7f4f"

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "sha256_file",
            "parameters": {
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
                "required": ["file_id"],
            },
        },
    }
]


def _tool_call(file_id: str = "file_002") -> dict[str, Any]:
    return {"function": {"name": "sha256_file", "arguments": {"file_id": file_id}}}


def _assistant(content: str = "", calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return message


def _ok() -> CallToolResult:
    return CallToolResult(
        content=[],
        structured_content={"ok": True, "digest_hex": DIGEST, "file_id": "file_002"},
    )


@pytest.mark.asyncio
async def test_finish_without_tool_call() -> None:
    session = AsyncMock()
    with patch.object(agent, "call_model", return_value=_assistant("直接回答")):
        answer = await agent.chat_turn(
            [], "你好", session=session, tools=TOOLS, model="fake", base_url="fake"
        )
    assert answer == "直接回答"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_call_then_answer_transitions() -> None:
    session = AsyncMock()
    session.call_tool.return_value = _ok()
    replies = [_assistant(calls=[_tool_call()]), _assistant(f"摘要 {DIGEST}")]
    messages: list[dict[str, Any]] = []
    with patch.object(agent, "call_model", side_effect=replies):
        answer = await agent.chat_turn(
            messages, "算摘要", session=session, tools=TOOLS, model="fake", base_url="fake"
        )
    assert answer == f"摘要 {DIGEST}"
    # REQUEST_MODEL -> DISPATCH_TOOLS -> REQUEST_MODEL -> FINISH 的消息顺序
    assert [message["role"] for message in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[2]["tool_call_id"] == "call_00_0"


@pytest.mark.asyncio
async def test_context_usage_updates_after_each_model_response() -> None:
    session = AsyncMock()
    session.call_tool.return_value = _ok()
    context = ContextMessage()
    replies = iter([
        (90, 10, _assistant("第一轮")),
        (110, 10, _assistant(calls=[_tool_call()])),
        (140, 20, _assistant("第二轮")),
    ])
    saved_usage: list[int] = []

    async def call_model(*args: Any, usage: dict[str, int], **kwargs: Any) -> dict[str, Any]:
        saved_usage.append(context.usage)
        prompt, completion, message = next(replies)
        usage.update(prompt_tokens=prompt, completion_tokens=completion)
        return message

    dispatch_tools = agent._dispatch_tools

    async def dispatch_after_usage_update(state: agent.LoopState, **kwargs: Any) -> None:
        assert state.usage == 20
        assert context.usage == 120
        await dispatch_tools(state, **kwargs)

    with (
        patch.object(agent, "call_model", side_effect=call_model),
        patch.object(agent, "_dispatch_tools", side_effect=dispatch_after_usage_update),
    ):
        for question in ("你好", "算摘要"):
            await agent.chat_turn(
                [], question, session=session, tools=TOOLS, model="fake", base_url="fake",
                context=context,
            )

    assert saved_usage == [0, 100, 120]
    assert [turn.usage for turn in context.history] == [100, 60]
    assert context.usage == 160


@pytest.mark.asyncio
async def test_max_steps_stops_with_reason() -> None:
    session = AsyncMock()
    session.call_tool.return_value = _ok()
    always = _assistant(calls=[_tool_call()])
    with (
        patch.object(agent, "call_model", return_value=always),
        pytest.raises(agent.LoopStopped) as excinfo,
    ):
        await agent.chat_turn(
            [],
            "无限调用",
            session=session,
            tools=TOOLS,
            model="fake",
            base_url="fake",
            max_steps=2,
        )
    assert excinfo.value.reason == "max_steps"
    assert excinfo.value.steps == 2
    assert session.call_tool.await_count == 2


def test_invalid_transition_is_rejected() -> None:
    state = agent.LoopState(run_id="run_test", messages=[], phase=agent.Phase.DISPATCH_TOOLS)
    with pytest.raises(RuntimeError, match="非法状态转移"):
        agent._enter(state, agent.Phase.FINISH)


@pytest.mark.asyncio
async def test_run_returns_structured_stop() -> None:
    settings = Settings.model_construct(
        CONTROLLER_MODEL="cfg-model",
        OLLAMA_BASE_URL="http://cfg-host:9999",
    )

    @asynccontextmanager
    async def fake_connect() -> Any:
        session = AsyncMock()
        session.call_tool.return_value = _ok()
        yield session, TOOLS

    always = _assistant(calls=[_tool_call()])
    with (
        patch.object(agent, "get_settings", return_value=settings),
        patch.object(agent, "connect_tools", fake_connect),
        patch.object(agent, "call_model", return_value=always),
    ):
        result = await agent.run(question="无限调用")

    assert result["status"] == "stopped"
    assert result["reason"] == "max_steps"
    assert result["steps"] == 5
    assert len(result["evidence"]) == 5
