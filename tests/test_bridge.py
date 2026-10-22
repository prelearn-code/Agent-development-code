"""MCP 工具发现：把 list_tools 转成模型可用的 function schema。"""

from unittest.mock import AsyncMock

import pytest
from mcp_integration.client.bridge import discover_tools


class _Tool:
    def __init__(self, name: str, schema: dict[str, object]) -> None:
        self.name = name
        self.description = "说明"
        self.input_schema = schema


class _ListResult:
    def __init__(self, tools: list[_Tool]) -> None:
        self.tools = tools


@pytest.mark.asyncio
async def test_discover_tools_maps_schema_and_preserves_x_resource() -> None:
    schema = {
        "type": "object",
        "properties": {"file_id": {"type": "string", "x-resource": "file"}},
        "required": ["file_id"],
    }
    session = AsyncMock()
    session.list_tools.return_value = _ListResult([_Tool("sha256_file", schema)])

    tools = await discover_tools(session)

    assert tools == [
        {
            "type": "function",
            "function": {
                "name": "sha256_file",
                "description": "说明",
                "parameters": schema,
            },
        }
    ]
    assert tools[0]["function"]["parameters"]["properties"]["file_id"]["x-resource"] == "file"


@pytest.mark.asyncio
async def test_discover_tools_returns_empty_list_for_no_tools() -> None:
    session = AsyncMock()
    session.list_tools.return_value = _ListResult([])
    assert await discover_tools(session) == []
