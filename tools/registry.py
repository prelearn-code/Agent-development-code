"""Validate a model tool proposal against the discovered MCP schema."""

from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]


def validate_tool_arguments(
    name: str,
    arguments: Any,
    tools: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """统一按工具 Schema 检查参数，返回业务错误；通过时返回 None。"""
    function = next(
        (tool["function"] for tool in tools if tool["function"]["name"] == name),
        None,
    )
    if function is None:
        return {"ok": False, "error": "unknown_tool", "message": "请使用已有工具。"}
    if not isinstance(arguments, dict):
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "工具参数必须是对象。",
        }

    schema = function["parameters"]
    # 缺失项使用空字符串；ID 字段兼容模型偶尔生成的占位词。
    missing_id_values = {"待补充", "待提供", "未提供", "未知", "unknown", "none", "null"}
    missing = [
        key
        for key in schema.get("required", [])
        if key not in arguments
        or (
            isinstance(arguments[key], str)
            and (
                not arguments[key].strip()
                or (key.endswith("_id") and arguments[key].strip().casefold() in missing_id_values)
            )
        )
    ]
    if missing:
        return {
            "ok": False,
            "error": "missing_arguments",
            "missing": missing,
            "message": "请用户补充 " + "、".join(missing) + "，不要自行猜测。",
        }

    errors = sorted(
        Draft202012Validator(schema).iter_errors(arguments),
        key=lambda error: ".".join(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        field = ".".join(str(part) for part in error.absolute_path) or "arguments"
        types = {
            "string": "字符串",
            "integer": "整数",
            "number": "数字",
            "boolean": "布尔值",
            "object": "对象",
            "array": "数组",
            "null": "null",
        }
        if error.validator == "type":
            expected = error.validator_value
            allowed = expected if isinstance(expected, list) else [expected]
            message = (
                field + " 必须是" + "或".join(types.get(str(item), str(item)) for item in allowed)
            )
        else:
            message = f"{field} 不符合工具要求（{error.validator}）"
        return {
            "ok": False,
            "error": "invalid_arguments",
            "field": field,
            "message": message + "，请用户修正。",
        }
    return None
