"""模型地址与模型名必须来自 Settings，不能硬编码在 Loop 里。"""

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from packages.app import agent
from packages.core.config import Settings

STUB_TOOLS: list[dict[str, Any]] = []


@asynccontextmanager
async def _fake_connect() -> Any:
    yield AsyncMock(), STUB_TOOLS


@pytest.mark.asyncio
async def test_run_uses_configured_model_and_base_url() -> None:
    seen: dict[str, Any] = {}

    def fake_call_model(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"role": "assistant", "content": "配置生效"}

    settings = Settings.model_construct(
        CONTROLLER_MODEL="cfg-model",
        OLLAMA_BASE_URL="http://cfg-host:9999",
    )
    with (
        patch.object(agent, "get_settings", return_value=settings),
        patch.object(agent, "connect_tools", _fake_connect),
        patch.object(agent, "call_model", side_effect=fake_call_model),
    ):
        result = await agent.run(question="测试")

    assert seen["model"] == "cfg-model"
    assert seen["base_url"] == "http://cfg-host:9999"
    assert result["status"] == "completed"
    assert result["answer"] == "配置生效"
    assert result["evidence"] == []


def test_cli_defaults_come_from_settings_and_can_be_overridden() -> None:
    settings = Settings.model_construct(
        CONTROLLER_MODEL="cfg-model",
        OLLAMA_BASE_URL="http://cfg-host:9999",
    )
    with patch.object(agent, "get_settings", return_value=settings):
        defaults = agent._build_parser().parse_args([])
        overridden = agent._build_parser().parse_args(
            ["--model", "cli-model", "--base-url", "http://cli-host:1234"]
        )

    assert defaults.model == "cfg-model"
    assert defaults.base_url == "http://cfg-host:9999"
    assert overridden.model == "cli-model"
    assert overridden.base_url == "http://cli-host:1234"
