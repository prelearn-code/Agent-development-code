"""风险策略闸门：L0 放行，L2+ 在 06 段之前一律拒绝。"""

import pytest
from packages.core.errors import ToolPermissionError
from packages.core.models import DEFAULT_POLICY, Policy, RiskLevel, ToolSpec
from packages.security.policy import check_policy


def _spec(name: str, risk: RiskLevel) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="测试用工具",
        input_schema={"type": "object", "properties": {}},
        risk_level=risk,
        read_only=risk == RiskLevel.L0_READ,
    )


@pytest.mark.parametrize(
    ("name", "risk"),
    [
        ("sha256_file", RiskLevel.L0_READ),
        ("sm2_verify_signature", RiskLevel.L0_READ),
    ],
)
def test_read_only_tools_pass(name: str, risk: RiskLevel) -> None:
    assert check_policy(_spec(name, risk)) is None


@pytest.mark.parametrize(
    ("name", "risk"),
    [
        ("sm2_sign_message", RiskLevel.L2_WRITE),
        ("sm2_enc", RiskLevel.L2_WRITE),
        ("sm2_dec", RiskLevel.L2_WRITE),
        ("sm2_generate_key", RiskLevel.L2_WRITE),
    ],
)
def test_write_tools_require_approval(name: str, risk: RiskLevel) -> None:
    with pytest.raises(ToolPermissionError) as excinfo:
        check_policy(_spec(name, risk))
    assert excinfo.value.context == {"tool": name, "risk": "L2_WRITE"}
    assert "审批" in str(excinfo.value)

 
def test_destructive_tools_are_rejected() -> None:
    with pytest.raises(ToolPermissionError):
        check_policy(_spec("destroy_key", RiskLevel.L4_DESTRUCTIVE))


def test_disallowed_policy_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        DEFAULT_POLICY,
        RiskLevel.L0_READ,
        Policy(auto=False, sandbox=False, approval=False, allowed=False),
    )
    with pytest.raises(ToolPermissionError) as excinfo:
        check_policy(_spec("sha256_file", RiskLevel.L0_READ))
    assert "不允许" in str(excinfo.value)
