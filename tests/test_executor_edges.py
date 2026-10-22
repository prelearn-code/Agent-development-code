"""execute_tool 的边界分支：非 dict 返回值、MCP 错误、未知资源类型等。"""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, TextContent
from packages.core.models import RiskLevel, ToolSpec
from tools import executor


def _noarg_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "noarg_tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _noarg_spec(schema: dict[str, Any] | None = None) -> ToolSpec:
    return ToolSpec(
        name="noarg_tool",
        description="",
        input_schema=schema or {"type": "object", "properties": {}},
        risk_level=RiskLevel.L0_READ,
        read_only=True,
    )


@pytest.mark.asyncio
async def test_non_dict_structured_payload_is_wrapped() -> None:
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[], structured_content=["a", "b"]
    )
    outcome = await executor.execute_tool(
        session, "noarg_tool", {}, [_noarg_tool()], specs={"noarg_tool": _noarg_spec()}
    )
    assert outcome.success is True
    assert outcome.data == ["a", "b"]
    assert outcome.metadata["wire"] == {"ok": True, "result": ["a", "b"]}


@pytest.mark.asyncio
async def test_mcp_is_error_becomes_tool_error() -> None:
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text="server exploded")],
        structured_content=None,
        is_error=True,
    )
    outcome = await executor.execute_tool(
        session, "noarg_tool", {}, [_noarg_tool()], specs={"noarg_tool": _noarg_spec()}
    )
    assert outcome.error_type == "ToolError"
    assert "server exploded" in str(outcome.metadata["wire"]["error"])


@pytest.mark.asyncio
async def test_unparsable_text_output_becomes_tool_error() -> None:
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text="not json")],
        structured_content=None,
    )
    outcome = await executor.execute_tool(
        session, "noarg_tool", {}, [_noarg_tool()], specs={"noarg_tool": _noarg_spec()}
    )
    assert outcome.error_type == "ToolError"
    assert outcome.metadata["wire"]["error"] == "invalid_tool_output"


@pytest.mark.asyncio
async def test_unknown_resource_kind_is_permission_error() -> None:
    schema = {
        "type": "object",
        "properties": {"file_id": {"type": "string", "x-resource": "weird"}},
        "required": ["file_id"],
    }
    tool = {
        "type": "function",
        "function": {"name": "noarg_tool", "parameters": schema},
    }
    session = AsyncMock()
    outcome = await executor.execute_tool(
        session,
        "noarg_tool",
        {"file_id": "file_002"},
        [tool],
        specs={"noarg_tool": _noarg_spec(schema)},
    )
    assert outcome.error_type == "ToolPermissionError"
    assert "未知资源类型" in str(outcome.metadata["message"])
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_string_resource_value_is_permission_error() -> None:
    schema = {
        "type": "object",
        "properties": {"file_id": {"x-resource": "file"}},
        "required": ["file_id"],
    }
    tool = {
        "type": "function",
        "function": {"name": "noarg_tool", "parameters": schema},
    }
    session = AsyncMock()
    outcome = await executor.execute_tool(
        session,
        "noarg_tool",
        {"file_id": 123},
        [tool],
        specs={"noarg_tool": _noarg_spec(schema)},
    )
    assert outcome.error_type == "ToolPermissionError"
    assert "必须是字符串" in str(outcome.metadata["message"])


@pytest.mark.asyncio
async def test_missing_key_resource_is_permission_error() -> None:
    """file_id 存在、key_id 不存在 → 资源闸门拒绝。"""
    schema = {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "x-resource": "file"},
            "key_id": {"type": "string", "x-resource": "key"},
        },
        "required": ["file_id", "key_id"],
    }
    tool = {"type": "function", "function": {"name": "noarg_tool", "parameters": schema}}
    session = AsyncMock()
    outcome = await executor.execute_tool(
        session,
        "noarg_tool",
        {"file_id": "file_002", "key_id": "not-configured"},
        [tool],
        specs={"noarg_tool": _noarg_spec(schema)},
    )
    assert outcome.error_type == "ToolPermissionError"
    assert outcome.metadata["key_id"] == "not-configured"
    session.call_tool.assert_not_awaited()
