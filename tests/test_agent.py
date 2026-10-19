import copy
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult
from packages.app import agent as client
from tools import executor, registry


@pytest.fixture
def tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "sm2_sign_message",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string"},
                        "key_id": {"type": "string"},
                    },
                    "required": ["file_id", "key_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sm2_generate_key",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        ({"file_id": "file_001"}, "missing_arguments"),
        ({"file_id": "file_001", "key_id": ""}, "missing_arguments"),
        ({"file_id": "file_001", "key_id": "  "}, "missing_arguments"),
        ({"file_id": "file_001", "key_id": 123}, "invalid_arguments"),
        ({"file_id": "file_001", "key_id": None}, "invalid_arguments"),
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
    result = await executor.execute_tool(session, "sm2_sign_message", arguments, tools)
    assert result["ok"] is False
    assert result["error"] == error
    if error == "missing_arguments":
        assert result["missing"] == ["key_id"]
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_tool_never_calls_mcp(tools: list[dict[str, Any]]) -> None:
    session = AsyncMock()
    result = await executor.execute_tool(session, "unknown", {}, tools)
    assert result["error"] == "unknown_tool"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("as_json", [False, True])
async def test_complete_arguments_call_mcp(
    tools: list[dict[str, Any]],
    as_json: bool,
) -> None:
    arguments = {"file_id": "file_001", "key_id": "sm2_test"}
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(content=[], structured_content={"ok": True})
    supplied = json.dumps(arguments) if as_json else arguments
    assert await executor.execute_tool(session, "sm2_sign_message", supplied, tools) == {"ok": True}
    session.call_tool.assert_awaited_once_with("sm2_sign_message", arguments=arguments)


@pytest.mark.asyncio
async def test_no_arguments_tool_accepts_empty_object(
    tools: list[dict[str, Any]],
) -> None:
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(content=[], structured_content={"ok": True})
    assert await executor.execute_tool(session, "sm2_generate_key", {}, tools) == {"ok": True}
    session.call_tool.assert_awaited_once_with("sm2_generate_key", arguments={})


@pytest.mark.asyncio
async def test_placeholder_word_is_judged_by_tool_not_schema(
    tools: list[dict[str, Any]],
) -> None:
    """占位词是合法字符串：schema 不再黑名单拦截，由业务层返回 unknown_key。"""
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[], structured_content={"ok": False, "error": "unknown_key"}
    )
    arguments = {"file_id": "file_001", "key_id": "待补充"}
    result = await executor.execute_tool(session, "sm2_sign_message", arguments, tools)
    session.call_tool.assert_awaited_once_with("sm2_sign_message", arguments=arguments)
    assert result == {"ok": False, "error": "unknown_key"}


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
@pytest.mark.parametrize("missing_values", [{}, {"key_id": ""}])
async def test_user_supplies_missing_parameter_next_turn(
    tools: list[dict[str, Any]],
    missing_values: dict[str, str],
) -> None:
    def call(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {"name": "sm2_sign_message", "arguments": arguments},
                }
            ],
        }

    responses = [
        call({"file_id": "file_001", **missing_values}),
        {"role": "assistant", "content": "请提供 key_id。"},
        call({"file_id": "file_001", "key_id": "sm2_test"}),
        {"role": "assistant", "content": "签名完成。"},
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
        assert await client.chat_turn(messages, "签名 file_001", **options) == "请提供 key_id。"
        session.call_tool.assert_not_awaited()
        assert await client.chat_turn(messages, "sm2_test", **options) == "签名完成。"
    session.call_tool.assert_awaited_once_with(
        "sm2_sign_message",
        arguments={"file_id": "file_001", "key_id": "sm2_test"},
    )
    feedback = json.loads(snapshots[1][-1]["content"])
    assert snapshots[1][-1]["role"] == "tool"
    assert feedback["error"] == "missing_arguments" and feedback["missing"] == ["key_id"]
    assert snapshots[2][1] == {"role": "user", "content": "签名 file_001"}
    assert snapshots[2][-2]["content"] == "请提供 key_id。"
    assert snapshots[2][-1]["content"] == "sm2_test"


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
