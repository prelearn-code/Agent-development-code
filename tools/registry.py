"""Validate a model tool proposal against the discovered MCP schema."""

from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from packages.core.models import RiskLevel, ToolSpec
from packages.core.resource_schema import RESOURCE_SCHEMA_KEY


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
    # 必填参数缺失（含只给了空白字符串）由 schema 层拒绝；
    # 占位词是否合法属于业务判断，交给工具自身（如 keystore 的 unknown_key）。
    missing = [
        key
        for key in schema.get("required", [])
        if key not in arguments
        or (isinstance(arguments[key], str) and not arguments[key].strip())
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


# ---------------------------------------------------------------- 工具规格表
# 风险等级是本地权威，不信任 MCP server 的 annotation（06 段原则）。
_RISK: dict[str, RiskLevel] = {
    "sha256_file": RiskLevel.L0_READ,
    "sm2_verify_signature": RiskLevel.L0_READ,
    # 写工具 02–04 段不注册，但规格先定义好，06 段恢复注册时直接用。
    "sm2_sign_message": RiskLevel.L2_WRITE,
    "sm2_enc": RiskLevel.L2_WRITE,
    "sm2_dec": RiskLevel.L2_WRITE,
    "sm2_generate_key": RiskLevel.L2_WRITE,
}

_MCP_SERVER = "crypto"


def build_toolspecs(tools: list[dict[str, Any]]) -> dict[str, ToolSpec]:
    """把 MCP 发现的工具与本地风险表合成 ToolSpec。

    schema/description 用发现结果（单一事实源），风险/只读用本地表。
    未在 _RISK 里声明的工具**不进表**：调用时按 ToolNotFoundError 拒绝（fail closed）。
    """
    specs: dict[str, ToolSpec] = {}
    for tool in tools:
        function = tool.get("function") or {}
        name = function.get("name")
        if not isinstance(name, str):
            continue
        risk = _RISK.get(name)
        if risk is None:
            continue
        specs[name] = ToolSpec(
            name=name,
            description=str(function.get("description", "")),
            input_schema=function.get("parameters", {}),
            risk_level=risk,
            read_only=risk == RiskLevel.L0_READ,
            source="mcp",
            mcp_server=_MCP_SERVER,
        )
    return specs


def resource_args(spec: ToolSpec) -> dict[str, str]:
    """从工具 schema 读资源参数（参数名 → 资源类型）。

    声明位置是 MCP 工具签名（`FileId` / `KeyId`），这里只负责读取；
    未标 `x-resource` 的参数不当作资源，交给服务端复查。
    """
    properties = spec.input_schema.get("properties") or {}
    return {
        name: schema[RESOURCE_SCHEMA_KEY]
        for name, schema in properties.items()
        if isinstance(schema, dict) and isinstance(schema.get(RESOURCE_SCHEMA_KEY), str)
    }
