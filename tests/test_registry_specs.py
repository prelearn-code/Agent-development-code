"""ToolSpec 规格表：schema 来自 MCP 发现，风险/只读来自本地表，资源语义来自 x-resource。"""

from typing import Any

from packages.core.models import RiskLevel
from packages.core.resource_schema import RESOURCE_SCHEMA_KEY
from tools.registry import build_toolspecs, resource_args


def _params(*, with_key: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "file_id": {"type": "string", RESOURCE_SCHEMA_KEY: "file"},
        "note": {"type": "string"},
    }
    if with_key:
        properties["key_id"] = {"type": "string", RESOURCE_SCHEMA_KEY: "key"}
    return {"type": "object", "properties": properties, "required": ["file_id"]}


def _tool(
    name: str,
    *,
    description: str = "说明",
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters if parameters is not None else _params(with_key=False),
        },
    }


def _discovered() -> list[dict[str, Any]]:
    return [
        _tool("sha256_file", description="摘要"),
        _tool("sm2_verify_signature", parameters=_params(with_key=True)),
        _tool("sm2_sign_message", parameters=_params(with_key=True)),
        _tool(
            "run_shell",
            description="未登记的工具",
            parameters={"type": "object", "properties": {}},
        ),
    ]


def test_builds_specs_only_for_known_tools() -> None:
    specs = build_toolspecs(_discovered())
    assert set(specs) == {"sha256_file", "sm2_verify_signature", "sm2_sign_message"}


def test_risk_level_drives_read_only_and_retry() -> None:
    specs = build_toolspecs(_discovered())
    read = specs["sha256_file"]
    write = specs["sm2_sign_message"]
    assert read.risk_level == RiskLevel.L0_READ
    assert read.read_only is True
    assert write.risk_level == RiskLevel.L2_WRITE
    assert write.read_only is False
    assert write.retry == 0  # ToolSpec 的守卫：非只读不得自动重试


def test_schema_and_description_come_from_discovery() -> None:
    specs = build_toolspecs(_discovered())
    spec = specs["sha256_file"]
    assert spec.description == "摘要"
    assert spec.input_schema["required"] == ["file_id"]
    assert spec.source == "mcp"
    assert spec.mcp_server == "crypto"


def test_resource_args_read_from_schema() -> None:
    specs = build_toolspecs(_discovered())
    assert resource_args(specs["sha256_file"]) == {"file_id": "file"}
    assert resource_args(specs["sm2_verify_signature"]) == {
        "file_id": "file",
        "key_id": "key",
    }


def test_unmarked_parameter_is_not_a_resource() -> None:
    specs = build_toolspecs(_discovered())
    assert "note" not in resource_args(specs["sha256_file"])


def test_resource_args_returns_a_copy() -> None:
    specs = build_toolspecs(_discovered())
    first = resource_args(specs["sha256_file"])
    first["file_id"] = "tampered"
    assert resource_args(specs["sha256_file"]) == {"file_id": "file"}


def test_empty_tool_list_yields_empty_specs() -> None:
    assert build_toolspecs([]) == {}


def test_non_string_tool_name_is_skipped() -> None:
    specs = build_toolspecs([{"function": {"name": 123, "parameters": {}}}])
    assert specs == {}
