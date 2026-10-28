"""异常层级。

规则：
  - 工具 handler 内部可以抛 Tool*Error，但 `execute_tool` 是唯一把它们
    转换为 `ToolResult` 的地方。
  - 模型客户端抛 `LLM*Error`，由 Loop 转成结构化的停止/失败结果。
  - 业务层不直接捕获工具/模型异常，取消（CancelledError）必须继续传播。

`reason` 是机器可读的稳定错误码，用于 `status/reason`、Trace 与 05 段落库；
`context` 保存定位问题的结构化字段（路径、状态码、耗时等）。
"""

from __future__ import annotations

from typing import Any, ClassVar

from packages.core.logging import scrub

_LLM_BODY_LIMIT = 500


class AgentError(Exception):
    """本项目所有自定义异常的基类。"""

    reason: ClassVar[str] = "agent_error"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        detail = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.message} ({detail})"


# ---------------------------------------------------------------- 工具异常


class ToolError(AgentError):
    """工具执行失败的基类。"""

    reason = "tool_error"


class ToolValidationError(ToolError):
    """入参不符合 input_schema 或业务规则。"""

    reason = "tool_validation_error"


class ToolPermissionError(ToolError):
    """RBAC 拒绝，或资源不在白名单内。"""

    reason = "tool_permission_denied"


# 兼容别名：权限拒绝在语义上也是一种 ToolError
ToolDeniedError = ToolPermissionError


class ToolTimeoutError(ToolError):
    """工具执行超时。注意：asyncio.wait_for 本身不负责杀子进程。"""

    reason = "tool_timeout"


class ToolOutputTooLargeError(ToolError):
    """输出超过限制，应截断或转为落盘引用。"""

    reason = "tool_output_too_large"


class ToolNotFoundError(ToolError):
    """模型请求了注册表里不存在的工具。必须显式拒绝，不静默忽略。"""

    reason = "tool_not_found"


class ToolExecutionError(ToolError):
    """工具执行本身的失败（意外异常、后端错误），由 executor 分类。"""

    reason = "tool_execution_error"


class SandboxError(ToolError):
    """隔离环境启动或执行失败。不可降级为宿主机执行。"""

    reason = "sandbox_error"


class BudgetExceededError(AgentError):
    """步骤数、总时限或 token 预算耗尽。"""

    reason = "budget_exceeded"


# ---------------------------------------------------------------- 模型异常


class LLMError(AgentError):
    """模型请求失败的基类；`reason` 直接作为结构化停止原因。"""

    reason = "llm_error"


class LLMConnectionError(LLMError):
    """连接失败：服务没起、地址错、传输中断。"""

    reason = "llm_connection_error"

    def __init__(self, *, base_url: str, detail: str = "") -> None:
        super().__init__("无法连接模型服务。", base_url=base_url, detail=detail)
        self.base_url = base_url


class LLMTimeoutError(LLMError):
    """单次模型请求超时（不是 Loop 的总 deadline）。"""

    reason = "llm_timeout"

    def __init__(self, *, timeout_s: float, base_url: str = "") -> None:
        super().__init__(
            f"模型请求超时（{timeout_s}s）。", timeout_s=timeout_s, base_url=base_url
        )
        self.timeout_s = timeout_s
        self.base_url = base_url


class LLMHTTPError(LLMError):
    """模型服务返回 4xx/5xx；响应体脱敏后截断保存，供 Trace 使用。"""

    def __init__(self, status_code: int, response_text: str) -> None:
        body = scrub(response_text)[:_LLM_BODY_LIMIT]
        super().__init__(
            f"模型服务返回 HTTP {status_code}。",
            status_code=status_code,
            response_text=body,
        )
        self.status_code = status_code
        self.response_text = body

    @property
    def reason(self) -> str:  # type: ignore[override]
        return f"llm_http_{self.status_code}"

    def __str__(self) -> str:
        return f"{self.message}（status={self.status_code}）"


class LLMParseError(LLMError):
    """响应不是合法 JSON，或缺少 `message` 字段。"""

    reason = "llm_parse_error"

    def __init__(self, response_text: str, *, detail: str = "") -> None:
        body = scrub(response_text)[:_LLM_BODY_LIMIT]
        super().__init__("模型响应无法解析。", detail=detail, response_text=body)
        self.response_text = body

    def __str__(self) -> str:
        return f"{self.message}（detail={self.context.get('detail', '')}）"


__all__ = [
    "AgentError",
    "BudgetExceededError",
    "LLMConnectionError",
    "LLMError",
    "LLMHTTPError",
    "LLMParseError",
    "LLMTimeoutError",
    "SandboxError",
    "ToolDeniedError",
    "ToolError",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolOutputTooLargeError",
    "ToolPermissionError",
    "ToolTimeoutError",
    "ToolValidationError",
]
