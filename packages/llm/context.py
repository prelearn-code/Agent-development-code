"""上下文组装：跨轮上下文状态 + 送模型前的消息合并。

分工：
  - `ContextMessage` 只放数据（system / 摘要 / 历史轮次 / 工具 schema），不做 IO；
  - `build_messages()` 决定送模型的顺序：system → 历史摘要 → 历史轮次 → 当前轮；
  - `ContextBuilder` 是后续的预算与截断入口（04 段剩余任务）。
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from packages.core.config import get_settings
from packages.core.loop_state import LoopState


def _default_system_message() -> dict[str, Any]:
    return {"role": "system", "content": ""}


def _default_num_ctx() -> int:
    return get_settings().LLM_NUM_CTX


@dataclass
class ContextMessage:
    """一次会话的上下文状态，跨轮复用。

    - `system_message`：固定的 system 消息（dict，不是字符串）
    - `history_compact`：被压缩历史生成的摘要消息（可为空）
    - `history`：已结束轮次的 LoopState 快照；当前轮不放这里
    - `tool_scheme`：本轮暴露给模型的工具 schema（与请求体里的 tools 同源）
    - `usage`：最近一次有计数的模型响应的输入加输出 token 数
    - `security_remaining` / `remaining`：预算余量，供 ContextBuilder 使用
    """

    system_message: dict[str, Any] = field(default_factory=_default_system_message)
    history_compact: list[dict[str, Any]] = field(default_factory=list)
    history: list[LoopState] = field(default_factory=list)
    tool_scheme: list[dict[str, Any]] = field(default_factory=list)
    usage: int = 0
    security_remaining: int = 740
    remaining: int = field(default_factory=_default_num_ctx)

    def add_turn(self, state: LoopState) -> None:
        """保存一轮结束时的状态快照。"""
        self.history.append(deepcopy(state))


def flatten_history(history: list[LoopState]) -> list[dict[str, Any]]:
    return [message for turn in history for message in turn.messages]


def build_messages(
    context: ContextMessage | None,
    current: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按固定顺序合并：system → 历史摘要 → 历史轮次 → 当前轮。

    `context` 为 None 时退化成"只发当前轮"，保持旧调用方（测试、单次 CLI）的行为。
    """
    if context is None:
        return list(current)
    messages: list[dict[str, Any]] = [context.system_message]
    messages.extend(context.history_compact)
    messages.extend(flatten_history(context.history))
    messages.extend(current)
    return messages


class ContextBuilder:
    """预算与截断的入口；当前只做原样返回，截断在 04 段剩余任务里补。"""

    def __init__(self, max_tokens: int, reserve_output: int = 1024) -> None:
        self.max_tokens = max_tokens
        self.reserve_output = reserve_output

    def build(self, *, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(messages)
