"""Convert the connected server's tool list to Ollama function schemas."""

from typing import Any

from mcp import ClientSession


async def discover_tools(session: ClientSession) -> list[dict[str, Any]]:
    discovered = await session.list_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in discovered.tools
    ]
