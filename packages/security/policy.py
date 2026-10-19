"""风险策略闸门：按 `ToolSpec.risk_level` 查 `DEFAULT_POLICY` 决定是否放行。

06 段之前，"需要审批" 等于 "拒绝"——默认拒绝，而不是默认放行。
这里不判断用户身份或项目归属（05/06 段），只做本地第一道风险闸门。
"""

from packages.core.errors import ToolPermissionError
from packages.core.models import DEFAULT_POLICY, ToolSpec


def check_policy(spec: ToolSpec) -> None:
    """不通过时抛 `ToolPermissionError`；通过返回 None。

    - `policy.allowed` 为 False：该风险等级被禁用
    - `policy.auto` 为 False：需要审批，06 段之前一律拒绝
    """
    policy = DEFAULT_POLICY[spec.risk_level]
    if not policy.allowed:
        raise ToolPermissionError(
            "该风险等级不允许执行。",
            tool=spec.name,
            risk=spec.risk_level.name,
        )
    if not policy.auto:
        raise ToolPermissionError(
            "该操作需要审批，第 06 段之前不允许执行。",
            tool=spec.name,
            risk=spec.risk_level.name,
        )
