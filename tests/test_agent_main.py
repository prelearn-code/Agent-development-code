"""交互式 main() 循环：输入一轮、打印回答、exit 退出。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from packages.app import agent


@asynccontextmanager
async def _fake_connect() -> AsyncIterator[tuple[AsyncMock, list[dict[str, Any]]]]:
    yield AsyncMock(), []


@pytest.mark.asyncio
async def test_main_prints_answer_and_exits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(agent, "connect_tools", _fake_connect)
    monkeypatch.setattr(
        agent,
        "call_model",
        AsyncMock(return_value={"role": "assistant", "content": "第一轮回答"}),
    )
    inputs = iter(["你好", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *args: next(inputs))
    monkeypatch.setattr("sys.argv", ["prog"])

    code = await agent.main()

    out = capsys.readouterr().out
    assert code == 0
    assert "助手<第一轮回答" in out


@pytest.mark.asyncio
async def test_main_reuses_model_client_across_user_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "connect_tools", _fake_connect)
    model = AsyncMock(return_value={"role": "assistant", "content": "回答"})
    monkeypatch.setattr(agent, "call_model", model)
    inputs = iter(["第一轮", "第二轮", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *args: next(inputs))
    monkeypatch.setattr("sys.argv", ["prog"])

    assert await agent.main() == 0
    assert model.await_count == 2
    first_client = model.await_args_list[0].kwargs["client"]
    assert model.await_args_list[1].kwargs["client"] is first_client
    assert first_client.is_closed
