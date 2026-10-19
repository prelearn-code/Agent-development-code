"""核心契约：ToolResult / ToolSpec / RiskLevel / Policy / Citation。

这些类型是 M1 起的稳定接口，M2~M6 的审批、MCP、Verifier 都建立在其上。
合同改动需同步调用方与测试，并按兼容性要求管理版本。

设计要点（来自 2026-10-10 修订）：
  - ToolResult 统一为 Pydantic BaseModel 泛型，序列化用 model_dump_json()。
    不用 dataclass，因为 dataclass 没有 model_dump_json 且嵌套校验能力弱。
  - 容器字段一律用 Field(default_factory=...)，避免可变默认值共享。
  - 空结果是 success=True，不是失败。这个区分决定 Verifier 是否该触发重试。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Awaitable, Callable, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RiskLevel(IntEnum):
    """风险分级。对应原验收文档 §16 的 L0~L4。"""

    L0_READ = 0
    L1_COMPUTE = 1
    L2_WRITE = 2
    L3_EXECUTE = 3
    L4_DESTRUCTIVE = 4


class Citation(BaseModel):
    """引用。page 允许 ±1 容差由 Verifier 决定，此处只承载事实。"""

    model_config = ConfigDict(frozen=True)

    document_id: str
    document_name: str
    chunk_id: str
    page: int | None = None
    page_end: int | None = None
    section: str | None = None
    quote: str | None = None


class ToolResult(BaseModel, Generic[T]):
    """所有工具的统一返回类型。

    契约：
      - 工具 handler 不抛异常，异常由 execute_tool 转为 ToolResult。
      - 空结果是 success=True、data 为空集合。
      - metadata 至少含 tool_name / duration_ms / retries / started_at。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    data: T | None = None
    error: str | None = None
    error_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)

    @classmethod
    def ok(
        cls,
        data: T | None = None,
        *,
        citations: list[Citation] | None = None,
        **metadata: Any,
    ) -> "ToolResult[T]":
        """成功。data 可以为空集合 —— 这不代表失败。"""
        return cls(
            success=True,
            data=data,
            metadata=metadata,
            citations=citations or [],
        )

    @classmethod
    def fail(
        cls,
        error: str,
        *,
        error_type: str | None = None,
        **metadata: Any,
    ) -> "ToolResult[T]":
        return cls(
            success=False,
            error=error,
            error_type=error_type or "ToolError",
            metadata=metadata,
        )


class ToolCall(BaseModel):
    """一次工具调用的请求。call_id 由应用生成，不依赖模型提供的 id。"""

    model_config = ConfigDict(frozen=True)

    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    step_index: int | None = None


class ToolSpec(BaseModel):
    """工具注册表条目。

    契约（由 scripts/check_tools.py 或测试强制）：
      - risk_level >= L2 且 read_only=False 时，retry 必须为 0（非幂等不自动重试）。
      - description 必须同时说明"什么时候用"和"什么时候不用"。
      - handler 必须是 async 且返回 ToolResult。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_s: float = 30.0
    permission: str = "public"
    risk_level: RiskLevel = RiskLevel.L0_READ
    read_only: bool = True
    retry: int = 0
    source: Literal["builtin", "mcp"] = "builtin"
    mcp_server: str | None = None
    handler: Callable[..., Awaitable[ToolResult[Any]]] | None = Field(default=None, exclude=True)

    def model_post_init(self, __context: Any) -> None:  # noqa: D105
        if not self.read_only and self.retry != 0:
            raise ValueError(
                f"工具 {self.name!r} 非只读（read_only=False）但有 retry={self.retry}；"
                "非幂等操作不得自动重试。"
            )
        if self.source == "mcp" and not self.mcp_server:
            raise ValueError(f"工具 {self.name!r} 标为 mcp 但未指定 mcp_server。")


class Policy(BaseModel):
    """风险等级对应的执行策略。见原验收文档 §16。"""

    model_config = ConfigDict(frozen=True)

    auto: bool
    sandbox: bool
    approval: Literal[False, True, "strong"]
    allowed: bool = True


# 默认策略表 —— M1 起生效，M5 完善威胁模型
DEFAULT_POLICY: dict[RiskLevel, Policy] = {
    RiskLevel.L0_READ: Policy(auto=True, sandbox=False, approval=False),
    RiskLevel.L1_COMPUTE: Policy(auto=True, sandbox=True, approval=False),
    RiskLevel.L2_WRITE: Policy(auto=False, sandbox=False, approval=True),
    RiskLevel.L3_EXECUTE: Policy(auto=False, sandbox=True, approval=True),
    RiskLevel.L4_DESTRUCTIVE: Policy(auto=False, sandbox=True, approval="strong"),
}


__all__ = [
    "Citation",
    "DEFAULT_POLICY",
    "Policy",
    "RiskLevel",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
]
