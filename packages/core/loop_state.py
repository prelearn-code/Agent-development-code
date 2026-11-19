"""Agent Loop 运行状态与会话历史共用的数据类型。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Phase(StrEnum):
    """Loop 的显式状态。"""

    REQUEST_MODEL = "request_model"  # 唯一的决策点：请求模型并决定下一步
    DISPATCH_TOOLS = "dispatch_tools"  # 执行 pending_calls，结果回传
    FINISH = "finish"  # 正常结束：模型不再提议工具
    STOPPED = "stopped"  # 预算/轮次耗尽：结束但不回答


@dataclass
class LoopState:
    """一次 Run 的控制流数据。

    只放数据、不放回调和连接：05 段可以直接把它序列化进 agent_runs/agent_steps，
    06 段恢复时据此决定从哪个 Phase 继续。pending_calls 也是 04 段流式累积的落点。
    """

    run_id: str
    messages: list[dict[str, Any]]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    step_index: int = 0
    phase: Phase = Phase.REQUEST_MODEL
    pending_calls: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    stop_reason: str = ""
    stop_detail: str = ""
    # 本轮的上下文净增量：每次有效响应相对上一次观测的变化量之和。
    # 一轮内没有收到用量时为 0。
    usage: int = 0
    tool_call_hash_list = dict[str,int]
