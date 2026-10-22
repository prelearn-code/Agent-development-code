"""核心契约：ToolResult / ToolSpec / DEFAULT_POLICY / 异常格式化。"""

import pytest
from packages.core.errors import ToolPermissionError
from packages.core.models import DEFAULT_POLICY, RiskLevel, ToolResult, ToolSpec
from pydantic import ValidationError


def test_tool_result_ok_and_fail() -> None:
    ok = ToolResult.ok({"x": 1}, tool_name="t")
    assert ok.success is True
    assert ok.data == {"x": 1}
    assert ok.metadata["tool_name"] == "t"

    failed = ToolResult[dict[str, int]].fail("boom", error_type="ToolError", detail=1)
    assert failed.success is False
    assert failed.error == "boom"
    assert failed.error_type == "ToolError"
    assert failed.metadata["detail"] == 1


def test_parameterized_tool_result_preserves_validation_and_serialization() -> None:
    result = ToolResult[list[int]].ok([1, 2], tool_name="test")
    restored = ToolResult[list[int]].model_validate_json(result.model_dump_json())
    assert restored.data == [1, 2]
    assert restored.metadata == {"tool_name": "test"}
    schema = ToolResult[list[int]].model_json_schema()
    assert schema["properties"]["data"]["anyOf"][0] == {
        "items": {"type": "integer"},
        "type": "array",
    }
    with pytest.raises(ValidationError):
        ToolResult[list[int]].model_validate({"success": True, "data": ["not an integer"]})
    failed = ToolResult[list[int]].fail("failure", error_type="ToolError")
    assert failed.data is None and failed.error_type == "ToolError"


def test_tool_result_containers_are_independent() -> None:
    first = ToolResult[list[int]].ok([])
    second = ToolResult[list[int]].ok([])
    first.metadata["tool_name"] = "first"
    assert second.metadata == {}
    assert first.citations is not second.citations


def test_tool_spec_rejects_non_idempotent_retry() -> None:
    with pytest.raises(ValueError):
        ToolSpec(name="w", description="", input_schema={}, read_only=False, retry=1)


def test_tool_spec_requires_mcp_server_for_mcp_source() -> None:
    with pytest.raises(ValueError):
        ToolSpec(name="w", description="", input_schema={}, source="mcp")


def test_default_policy_matrix() -> None:
    assert DEFAULT_POLICY[RiskLevel.L0_READ].auto is True
    assert DEFAULT_POLICY[RiskLevel.L2_WRITE].auto is False
    assert DEFAULT_POLICY[RiskLevel.L4_DESTRUCTIVE].approval == "strong"
    assert DEFAULT_POLICY[RiskLevel.L4_DESTRUCTIVE].auto is False


def test_agent_error_formats_context() -> None:
    err = ToolPermissionError("denied", file_id="file_001")
    assert "denied" in str(err)
    assert "file_id='file_001'" in str(err)
