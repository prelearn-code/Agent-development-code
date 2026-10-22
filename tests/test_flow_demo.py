"""把模型/工具调用过程打印出来，便于和直接调用 CLI 的输出对照。

    pytest -s -q --flow tests/test_flow_demo.py
"""

import copy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult
from packages.app import agent as client
from packages.core.config import Settings
from tools import executor

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "sha256_file",
            "description": "计算摘要",
            "parameters": {
                "type": "object",
                "properties": {"file_id": {"type": "string", "x-resource": "file"}},
                "required": ["file_id"],
            },
        },
    }
]

ARGS = {"file_id": "file_001"}


@pytest.fixture
def sandbox(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "data"
    directory = root / "file_001"
    directory.mkdir(parents=True)
    (directory / "data.md").write_text("content", encoding="utf-8")
    settings = Settings.model_construct(
        CRYPTO_DATA_ROOT=str(root), CRYPTO_MAX_FILE_BYTES=100
    )
    monkeypatch.setattr(executor, "get_settings", lambda: settings)
    return root


def _assistant(content: str = "", calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [{"function": call} for call in calls]
    return message


@pytest.mark.asyncio
async def test_flow_tool_call_roundtrip(flow, sandbox) -> None:
    """完整的 提议 → 执行 → 回传 → 回答 过程。"""
    responses = [
        _assistant(calls=[{"name": "sha256_file", "arguments": ARGS}]),
        _assistant("摘要完成。"),
    ]
    snapshots: list[list[dict[str, Any]]] = []

    def respond(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        snapshots.append(copy.deepcopy(messages))
        return responses[len(snapshots) - 1]

    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[],
        structured_content={
            "ok": True,
            "algorithm": "SHA-256",
            "digest_hex": "a" * 64,
            "file_id": "file_001",
        },
    )
    messages = [client.SYSTEM_PROMPT.copy()]
    with patch.object(client, "call_model", side_effect=respond):
        answer = await client.chat_turn(
            messages,
            "计算 file_001 的摘要",
            session=session,
            tools=TOOLS,
            model="fake",
            base_url="fake",
        )

    flow("最终回答", answer)
    flow("完整对话（user / assistant.tool_calls / tool / assistant）", snapshots[-1])
    assert answer == "摘要完成。"
    session.call_tool.assert_awaited_once_with("sha256_file", arguments=ARGS)


@pytest.mark.asyncio
async def test_flow_permission_denied(flow) -> None:
    """被资源闸门拒绝时的调用过程：MCP 完全不被调用。"""
    arguments = {"file_id": "../../etc/passwd"}
    session = AsyncMock()
    outcome = await executor.execute_tool(session, "sha256_file", arguments, TOOLS)
    flow(
        "工具调用被拒",
        {
            "tool": "sha256_file",
            "arguments": arguments,
            "success": outcome.success,
            "error_type": outcome.error_type,
            "wire": outcome.metadata["wire"],
            "mcp_called": session.call_tool.await_count,
        },
    )
    assert outcome.error_type == "ToolPermissionError"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_flow_business_failure(flow, sandbox) -> None:
    """MCP 返回业务失败时的报文。"""
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[],
        structured_content={"ok": False, "error": "invalid_file", "message": "文件不合法"},
    )
    outcome = await executor.execute_tool(session, "sha256_file", ARGS, TOOLS)
    flow(
        "MCP 业务失败",
        {
            "success": outcome.success,
            "error": outcome.error,
            "message": outcome.metadata["message"],
            "wire": outcome.metadata["wire"],
        },
    )
    assert outcome.success is False
