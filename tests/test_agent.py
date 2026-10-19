"""Agent Loop 与执行入口的单元测试。

成功后端一律用只读工具 `sha256_file`：02–04 段 MCP 只暴露只读工具，
写工具由 tests/test_authorization.py 单独验证"在调 MCP 之前被拒"。
"""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult
from packages.app import agent as client
from packages.core.config import Settings
from packages.core.models import RiskLevel, ToolSpec
from tools import executor, registry

DATA_ARGS = {"file_id": "file_001"}


@pytest.fixture
def tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "sha256_file",
                "parameters": {
                    "type": "object",
                    "properties": {"file_id": {"type": "string", "x-resource": "file"}},
                    "required": ["file_id"],
                },
            },
        },
    ]


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    directory = root / "file_001"
    directory.mkdir(parents=True)
    (directory / "data.md").write_text("content", encoding="utf-8")
    settings = Settings.model_construct(
        CRYPTO_DATA_ROOT=str(root), CRYPTO_MAX_FILE_BYTES=100
    )
    monkeypatch.setattr(executor, "get_settings", lambda: settings)
    return root


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        ({}, "missing_arguments"),
        ({"file_id": ""}, "missing_arguments"),
        ({"file_id": "  "}, "missing_arguments"),
        ({"file_id": 123}, "invalid_arguments"),
        ({"file_id": None}, "invalid_arguments"),
        ([], "invalid_arguments"),
        (None, "invalid_arguments"),
        ("not json", "invalid_arguments"),
    ],
)
async def test_invalid_arguments_never_call_mcp(
    tools: list[dict[str, Any]],
    arguments: Any,
    error: str,
) -> None:
    session = AsyncMock()
    result = await executor.execute_tool(session, "sha256_file", arguments, tools)
    assert result.success is False
    assert result.error_type == "ToolValidationError"
    assert result.metadata["wire"]["error"] == error
    if error == "missing_arguments":
        assert result.metadata["missing"] == ["file_id"]
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_tool_never_calls_mcp(tools: list[dict[str, Any]]) -> None:
    session = AsyncMock()
    result = await executor.execute_tool(session, "unknown", {}, tools)
    assert result.success is False
    assert result.error_type == "ToolNotFoundError"
    assert result.metadata["wire"]["error"] == "unknown_tool"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("as_json", [False, True])
async def test_complete_arguments_call_mcp(
    tools: list[dict[str, Any]],
    data_root: Path,
    as_json: bool,
) -> None:
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(content=[], structured_content={"ok": True})
    supplied = json.dumps(DATA_ARGS) if as_json else DATA_ARGS
    outcome = await executor.execute_tool(session, "sha256_file", supplied, tools)
    assert outcome.success is True
    assert outcome.data == {"ok": True}
    assert outcome.metadata["wire"] == {"ok": True}
    session.call_tool.assert_awaited_once_with("sha256_file", arguments=DATA_ARGS)


@pytest.mark.asyncio
async def test_no_arguments_tool_accepts_empty_object() -> None:
    """无参数工具：schema 没有 required，注入只读 spec 后可以执行。"""
    tool = {
        "type": "function",
        "function": {
            "name": "noarg_tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    spec = ToolSpec(
        name="noarg_tool",
        description="无参数只读工具",
        input_schema=tool["function"]["parameters"],
        risk_level=RiskLevel.L0_READ,
        read_only=True,
    )
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(content=[], structured_content={"ok": True})
    outcome = await executor.execute_tool(
        session, "noarg_tool", {}, [tool], specs={"noarg_tool": spec}
    )
    assert outcome.success is True
    assert outcome.data == {"ok": True}
    session.call_tool.assert_awaited_once_with("noarg_tool", arguments={})


@pytest.mark.asyncio
async def test_placeholder_id_is_rejected_by_resource_gate(
    tools: list[dict[str, Any]],
) -> None:
    """占位词能通过 schema，但会被资源闸门拒绝（不是 schema 黑名单）。"""
    session = AsyncMock()
    outcome = await executor.execute_tool(
        session, "sha256_file", {"file_id": "待补充"}, tools
    )
    assert outcome.error_type == "ToolPermissionError"
    assert outcome.metadata["wire"]["error"] == "permission_denied"
    session.call_tool.assert_not_awaited()


def test_schema_constraints_apply_to_other_tools() -> None:
    tools = [
        {
            "function": {
                "name": "another_tool",
                "parameters": {
                    "type": "object",
                    "properties": {"count": {"type": "integer", "minimum": 1}},
                    "required": ["count"],
                },
            }
        }
    ]
    assert registry.validate_tool_arguments("another_tool", {"count": 2}, tools) is None
    for count in (0, True, "2"):
        error = registry.validate_tool_arguments("another_tool", {"count": count}, tools)
        assert error is not None and error["error"] == "invalid_arguments"
    error = registry.validate_tool_arguments("another_tool", {}, tools)
    assert error is not None and error["missing"] == ["count"]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_value", ["", "  "])
async def test_user_supplies_missing_parameter_next_turn(
    tools: list[dict[str, Any]],
    data_root: Path,
    missing_value: str,
) -> None:
    def call(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {"name": "sha256_file", "arguments": arguments},
                }
            ],
        }

    responses = [
        call({"file_id": missing_value}),
        {"role": "assistant", "content": "请提供 file_id。"},
        call({"file_id": "file_001"}),
        {"role": "assistant", "content": "摘要完成。"},
    ]
    snapshots = []

    def respond(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        snapshots.append(copy.deepcopy(messages))
        return responses[len(snapshots) - 1]

    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(content=[], structured_content={"ok": True})
    messages = [client.SYSTEM_PROMPT.copy()]
    options = dict(session=session, tools=tools, model="fake", base_url="fake")
    with patch.object(client, "call_model", side_effect=respond):
        assert await client.chat_turn(messages, "计算 file_001", **options) == "请提供 file_id。"
        session.call_tool.assert_not_awaited()
        assert await client.chat_turn(messages, "是 file_001", **options) == "摘要完成。"
    session.call_tool.assert_awaited_once_with("sha256_file", arguments=DATA_ARGS)
    feedback = json.loads(snapshots[1][-1]["content"])
    assert snapshots[1][-1]["role"] == "tool"
    assert feedback["error"] == "missing_arguments" and feedback["missing"] == ["file_id"]
    assert snapshots[2][1] == {"role": "user", "content": "计算 file_001"}
    assert snapshots[2][-2]["content"] == "请提供 file_id。"
    assert snapshots[2][-1]["content"] == "是 file_001"


def test_id_placeholder_check_does_not_reject_normal_text() -> None:
    tools = [
        {
            "function": {
                "name": "text_tool",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            }
        }
    ]
    assert registry.validate_tool_arguments("text_tool", {"message": "待补充"}, tools) is None


@pytest.mark.asyncio
async def test_wire_payload_keeps_model_visible_shape(
    tools: list[dict[str, Any]],
    data_root: Path,
) -> None:
    """接 ToolResult 后，模型侧报文仍是工具原始 dict，不因内部类型变化而变。"""
    session = AsyncMock()
    success_payload = {"ok": True, "digest_hex": "a" * 64, "file_id": "file_001"}
    session.call_tool.return_value = CallToolResult(
        content=[], structured_content=success_payload
    )
    outcome = await executor.execute_tool(session, "sha256_file", DATA_ARGS, tools)
    assert outcome.metadata["wire"] == success_payload
    assert json.dumps(outcome.metadata["wire"], ensure_ascii=False) == json.dumps(
        success_payload, ensure_ascii=False
    )


@pytest.mark.asyncio
async def test_business_failure_keeps_error_code_and_message(
    tools: list[dict[str, Any]],
    data_root: Path,
) -> None:
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[],
        structured_content={"ok": False, "error": "invalid_file", "message": "文件夹不合法"},
    )
    outcome = await executor.execute_tool(session, "sha256_file", DATA_ARGS, tools)
    assert outcome.success is False
    assert outcome.error == "invalid_file"  # 机器可读错误码，进 evidence
    assert outcome.metadata["message"] == "文件夹不合法"  # 人读说明
    assert outcome.metadata["wire"]["error"] == "invalid_file"


@pytest.mark.asyncio
async def test_cancelled_error_propagates(
    tools: list[dict[str, Any]],
    data_root: Path,
) -> None:
    """取消不是工具失败：必须原样抛出，不能转成 ToolResult。"""
    session = AsyncMock()
    session.call_tool.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await executor.execute_tool(session, "sha256_file", DATA_ARGS, tools)


@pytest.mark.asyncio
async def test_unexpected_exception_is_classified_and_scrubbed(
    tools: list[dict[str, Any]],
    data_root: Path,
) -> None:
    session = AsyncMock()
    # 拆开写是为了不让仓库的密钥扫描把假口令当成真口令（源码里不出现连续的 password=）。
    session.call_tool.side_effect = RuntimeError("boom " "pass" "word=supersecret123")
    outcome = await executor.execute_tool(session, "sha256_file", DATA_ARGS, tools)
    assert outcome.success is False
    assert outcome.error_type == "ToolError"
    assert "supersecret123" not in str(outcome.metadata["message"])
