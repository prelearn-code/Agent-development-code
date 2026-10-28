"""模型请求失败：Loop 转成 status=failed + reason，而不是崩溃。"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from packages.app import agent
from packages.core.errors import (
    LLMConnectionError,
    LLMHTTPError,
    LLMParseError,
    LLMTimeoutError,
)


@asynccontextmanager
async def _fake_model_client():
    yield object()


@asynccontextmanager
async def _fake_connect():
    yield AsyncMock(), []


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            LLMConnectionError(base_url="http://127.0.0.1:9/api/chat", detail="refused"),
            "llm_connection_error",
        ),
        (
            LLMTimeoutError(timeout_s=1, base_url="http://127.0.0.1:11434/api/chat"),
            "llm_timeout",
        ),
        (LLMHTTPError(404, "model not found"), "llm_http_404"),
        (LLMParseError("<html>", detail="JSONDecodeError"), "llm_parse_error"),
    ],
)
@pytest.mark.asyncio
async def test_run_reports_llm_failure(error: Exception, reason: str) -> None:
    with (
        patch.object(agent, "create_model_client", _fake_model_client),
        patch.object(agent, "connect_tools", _fake_connect),
        patch.object(agent, "call_model", side_effect=error),
    ):
        result = await agent.run(question="计算教学文件 file_002 的 SHA-256 摘要")

    assert result["status"] == "failed"
    assert result["reason"] == reason
    assert result["detail"]
    assert result["steps"] == 0
    assert result["evidence"] == []


@pytest.mark.asyncio
async def test_loop_stopped_message_contains_detail() -> None:
    error = LLMHTTPError(500, "boom")
    stopped = agent.LoopStopped("llm_http_500", 2, str(error))
    assert "llm_http_500" in str(stopped)
    assert "500" in str(stopped)
    assert isinstance(stopped, RuntimeError)
