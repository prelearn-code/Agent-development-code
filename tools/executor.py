"""Call a discovered MCP tool only after argument validation."""

import json
from typing import Any

from mcp import ClientSession

from tools.registry import validate_tool_arguments


async def execute_tool(
    session: ClientSession,
    name: str,
    arguments: Any,
    tools: list[dict[str, Any]],
) -> Any:
    """先校验参数，再执行 MCP 工具。"""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "invalid_arguments",
                "message": "工具参数不是合法 JSON，请修正参数。",
            }
    error = validate_tool_arguments(name, arguments, tools)
    if error is not None:
        return error
    result = await session.call_tool(name, arguments=arguments)
    # 做容错，防止模型返回值有问题
    text = "\n".join(block.text for block in result.content if block.type == "text")
    if result.is_error:
        return {"ok": False, "error": text}

    # 真正的返回还是result.structured_content,已经是标准的数据了
    return result.structured_content if result.structured_content is not None else json.loads(text)
