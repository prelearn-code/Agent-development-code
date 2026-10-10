"""异常层级。

规则：工具 handler 内部可以抛这些异常，但 execute_tool 是唯一把它们
转换为 ToolResult 的地方。路由与节点层不直接捕获工具异常。
"""

from __future__ import annotations

from typing import Any


class AgentError(Exception):
    """本项目所有自定义异常的基类。"""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        detail = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.message} ({detail})"


class ToolError(AgentError):
    """工具执行失败的基类。"""


class ToolValidationError(ToolError):
    """入参不符合 input_schema 或业务规则。"""


class ToolPermissionError(ToolError):
    """RBAC 拒绝，或资源不在白名单内。"""


# 兼容别名：权限拒绝在语义上也是一种 ToolError
ToolDeniedError = ToolPermissionError


class ToolTimeoutError(ToolError):
    """工具执行超时。注意：asyncio.wait_for 本身不负责杀子进程。"""


class ToolOutputTooLargeError(ToolError):
    """输出超过限制，应截断或转为落盘引用。"""


class ToolNotFoundError(ToolError):
    """模型请求了注册表里不存在的工具。必须显式拒绝，不静默忽略。"""


class SandboxError(ToolError):
    """隔离环境启动或执行失败。不可降级为宿主机执行。"""


class BudgetExceededError(AgentError):
    """步骤数、总时限或 token 预算耗尽。"""


__all__ = [
    "AgentError",
    "BudgetExceededError",
    "SandboxError",
    "ToolDeniedError",
    "ToolError",
    "ToolNotFoundError",
    "ToolOutputTooLargeError",
    "ToolPermissionError",
    "ToolTimeoutError",
    "ToolValidationError",
]
