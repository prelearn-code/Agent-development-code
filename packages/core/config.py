"""应用配置。

契约：Settings 的字段名（大写）必须与 .env.example 的键完全一致，
由 scripts/selftest.py 自动校验，因此不存在"文档里有、代码里没有"的配置项。

注意：暂无默认值的可选集成项用空字符串表示"未配置"，
不要在 import 时抛异常——Phase 0 时数据库和向量库都还不存在。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用 ----
    APP_ENV: Literal["dev", "test", "prod"] = "dev"
    APP_LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    API_KEY_HEADER: str = "X-API-Key"

    # ---- LLM / Ollama ----
    # 默认值是 WSL 访问 Windows 宿主的形态；宿主 IP 随 WSL 重建会变，
    # 用 `ip route show default | awk '{print $3}'` 重新确认。
    OLLAMA_BASE_URL: str = "http://172.26.0.1:11434"
    CONTROLLER_MODEL: str = "qwen3:4b"
    CONTROLLER_MODEL_SMALL: str = "qwen3:4b"
    CONTROLLER_MODEL_LARGE: str = ""  # M5 才需要
    JUDGE_MODEL: str = ""  # M5 才需要，必须与生成模型不同
    LLM_TIMEOUT_S: int = 120
    LLM_THINK: bool = False  # 固定 false，否则 token 消耗无法跨配置比较
    LLM_NUM_CTX: int = 8192

    # ---- 数据库（M2 引入）----
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "lpa"
    DATABASE_URL: str = ""  # 应用连接，非超管
    AUDIT_DATABASE_URL: str = ""  # 只具备 INSERT 权限的角色

    # ---- 向量库（M3 引入）----
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "knowledge_v1"
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIM: int = 1024

    # ---- 路径与安全 ----
    ALLOWED_READ_ROOTS: str = "./data/documents,./data/datasets"
    SANDBOX_IMAGE: str = ""  # M1 首次执行不可信代码前必须填写
    SANDBOX_TIMEOUT_S: int = 60
    SANDBOX_MEMORY_MB: int = 2048
    SANDBOX_PIDS_LIMIT: int = 128
    SANDBOX_NETWORK: Literal["none", "bridge"] = "none"

    # ---- MCP（M4 引入）----
    MCP_TRANSPORT: Literal["stdio", "http"] = "stdio"
    MCP_LOG_DIR: str = "./data/mcp-logs"
    MCP_FS_ROOT: str = "./data"

    # ---- 评测 ----
    # 串行是刻意的：单 GPU 下并发只会互相排队，让延迟指标不可比。
    EVAL_CONCURRENCY: int = 1
    EVAL_DATASET: str = "eval/datasets/eval-v1.jsonl"

    # ---- 派生属性 ----
    @property
    def allowed_read_roots(self) -> list[Path]:
        return [
            Path(p.strip()).resolve()
            for p in self.ALLOWED_READ_ROOTS.split(",")
            if p.strip()
        ]

    @property
    def judge_model_or_default(self) -> str:
        """Judge 必须与生成模型不同；未配置时回退到 LARGE。"""
        return self.JUDGE_MODEL or self.CONTROLLER_MODEL_LARGE

    @field_validator("OLLAMA_BASE_URL", "QDRANT_URL")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("DATABASE_URL", "AUDIT_DATABASE_URL")
    @classmethod
    def _check_dsn_prefix(cls, v: str) -> str:
        if v and not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DSN 必须以 postgresql+asyncpg:// 开头")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
