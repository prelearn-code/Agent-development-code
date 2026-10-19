"""Call a discovered MCP tool only after argument validation.

执行工具的唯一入口：模型提议、MCP 结果和异常都在这里收敛成 ToolResult。
`session.call_tool` 只允许出现在本模块（由 tests/test_boundaries.py 强制）。
"""

import asyncio
import json
import time
from typing import Any

from mcp import ClientSession
from packages.core.config import get_settings
from packages.core.errors import ToolPermissionError
from packages.core.logging import scrub
from packages.core.models import ToolResult, ToolSpec
from packages.core.resource_schema import ResourceKind
from packages.security import resources as security
from packages.security.policy import check_policy

from tools.registry import build_toolspecs, resource_args, validate_tool_arguments

# schema 校验返回的业务错误码 → 契约异常类型
_ERROR_TYPES = {
    "unknown_tool": "ToolNotFoundError",
    "invalid_arguments": "ToolValidationError",
    "missing_arguments": "ToolValidationError",
}


def _fail(
    *,
    code: str,
    error_type: str,
    message: str,
    wire: dict[str, Any],
    tool_name: str,
    duration_ms: float,
    **context: Any,
) -> ToolResult[Any]:
    """统一构造失败结果。

    - error 存机器可读的错误码（evidence / Trace 用）
    - message 存人读的说明（同时保留在 wire 里给模型看）
    """
    return ToolResult.fail(
        code,
        error_type=error_type,
        message=message,
        tool_name=tool_name,
        duration_ms=round(duration_ms, 3),
        wire=wire,
        **context,
    )


def _resolve_resource(kind: str, value: Any) -> None:
    """按 schema 里的 `x-resource` 在调 MCP 之前做资源边界检查。"""
    if not isinstance(value, str):
        raise ToolPermissionError("资源 ID 必须是字符串。", resource=kind)
    if kind == ResourceKind.FILE:
        settings = get_settings()
        security.require_message_file(
            value,
            max_bytes=settings.CRYPTO_MAX_FILE_BYTES,
            root=settings.crypto_data_root,
        )
    elif kind == ResourceKind.KEY:
        security.require_key(value)
    else:
        raise ToolPermissionError("未知资源类型。", resource=kind)


async def execute_tool(
    session: ClientSession,
    name: str,
    arguments: Any,
    tools: list[dict[str, Any]],
    *,
    specs: dict[str, ToolSpec] | None = None,
) -> ToolResult[Any]:
    """先校验参数、登记、资源与风险，再执行 MCP 工具。

    顺序固定：schema → 登记 → 资源 → 策略 → call_tool。
    - 预期失败转成 success=False，不抛异常
    - 意外异常在这一层分类；CancelledError 必须继续传播
    - metadata["wire"] 保存模型可见的原始 dict（成功=工具结果，失败={ok:false,...}）
    """
    started = time.monotonic()

    def elapsed_ms() -> float:
        return (time.monotonic() - started) * 1000

    if specs is None:
        specs = build_toolspecs(tools)

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            wire = {
                "ok": False,
                "error": "invalid_arguments",
                "message": "工具参数不是合法 JSON，请修正参数。",
            }
            return _fail(
                code="invalid_arguments",
                error_type="ToolValidationError",
                message=str(wire["message"]),
                wire=wire,
                tool_name=name,
                duration_ms=elapsed_ms(),
            )

    error = validate_tool_arguments(name, arguments, tools)
    if error is not None:
        message = str(error.get("message", "工具参数无效。"))
        error_type = _ERROR_TYPES.get(str(error.get("error")), "ToolValidationError")
        context = {"missing": error["missing"]} if "missing" in error else {}
        return _fail(
            code=str(error.get("error", "invalid_arguments")),
            error_type=error_type,
            message=message,
            wire=error,
            tool_name=name,
            duration_ms=elapsed_ms(),
            **context,
        )

    spec = specs.get(name)
    if spec is None:
        wire = {"ok": False, "error": "unknown_tool", "message": "请使用已有工具。"}
        return _fail(
            code="unknown_tool",
            error_type="ToolNotFoundError",
            message=str(wire["message"]),
            wire=wire,
            tool_name=name,
            duration_ms=elapsed_ms(),
        )

    try:
        for arg_name, kind in resource_args(spec).items():
            value = arguments.get(arg_name) if isinstance(arguments, dict) else None
            if value is None:
                continue  # 可选资源参数允许省略
            _resolve_resource(kind, value)
        check_policy(spec)
    except ToolPermissionError as exc:
        wire = {"ok": False, "error": "permission_denied", "message": str(exc)}
        return _fail(
            code="permission_denied",
            error_type="ToolPermissionError",
            message=str(exc),
            wire=wire,
            tool_name=name,
            duration_ms=elapsed_ms(),
            **exc.context,
        )

    try:
        result = await session.call_tool(name, arguments=arguments)
    except asyncio.CancelledError:
        raise  # 取消不是失败，不能让上层误以为工具返回了结果
    except Exception as exc:  # noqa: BLE001 - 意外异常在这一层分类，不向上冒泡
        message = scrub(str(exc)) or "工具执行失败。"
        wire = {"ok": False, "error": "tool_execution_failed", "message": message}
        return _fail(
            code="tool_execution_failed",
            error_type="ToolError",
            message=message,
            wire=wire,
            tool_name=name,
            duration_ms=elapsed_ms(),
        )

    text = "\n".join(block.text for block in result.content if block.type == "text")
    if result.structured_content is not None:
        payload: Any = result.structured_content
    else:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            message = scrub(text) or "工具返回了无法解析的内容。"
            wire = {"ok": False, "error": "invalid_tool_output", "message": message}
            return _fail(
                code="invalid_tool_output",
                error_type="ToolError",
                message=message,
                wire=wire,
                tool_name=name,
                duration_ms=elapsed_ms(),
            )

    if result.is_error:
        message = scrub(text) or "工具执行失败。"
        wire = {"ok": False, "error": message}
        return _fail(
            code="tool_execution_failed",
            error_type="ToolError",
            message=message,
            wire=wire,
            tool_name=name,
            duration_ms=elapsed_ms(),
        )

    if not isinstance(payload, dict):
        return ToolResult.ok(
            payload,
            tool_name=name,
            duration_ms=round(elapsed_ms(), 3),
            wire={"ok": True, "result": payload},
        )

    # 工具 handler 不抛异常，用 {"ok": false} 表达业务失败；沿用旧语义。
    if payload.get("ok") is False:
        message = str(payload.get("message", payload.get("error", "工具执行失败。")))
        return _fail(
            code=str(payload.get("error", "tool_error")),
            error_type="ToolError",
            message=message,
            wire=payload,
            tool_name=name,
            duration_ms=elapsed_ms(),
        )

    return ToolResult.ok(
        payload,
        tool_name=name,
        duration_ms=round(elapsed_ms(), 3),
        wire=payload,
    )
