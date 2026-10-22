"""Async model requests preserve the wire contract, timeout and client ownership."""

import asyncio
import json
from typing import Any

import httpx
import pytest
from packages.core.config import Settings
from packages.llm import client


@pytest.mark.asyncio
async def test_model_request_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["timeout"] = request.extensions["timeout"]
        seen["body"] = json.loads(request.content)
        assert request.method == "POST"
        assert request.headers["content-type"] == "application/json"
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    owned = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(client, "create_model_client", lambda: owned)
    monkeypatch.setattr(client, "get_settings", lambda: Settings.model_construct(LLM_TIMEOUT_S=7))
    messages = [{"role": "user", "content": "计算摘要"}]
    tools = [{"type": "function", "function": {"name": "sha256_file"}}]

    assert await client.call_model(messages, tools, "test-model", "http://localhost:11434/") == {
        "role": "assistant",
        "content": "ok",
    }
    assert seen == {
        "url": "http://localhost:11434/api/chat",
        "timeout": {"connect": 7, "read": 7, "write": 7, "pool": 7},
        "body": {
            "model": "test-model",
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0},
        },
    }
    assert owned.is_closed


@pytest.mark.asyncio
async def test_shared_model_client_is_reused_and_closed_by_owner() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as shared:
        for _ in range(2):
            await client.call_model([], [], "test-model", "http://localhost:11434", client=shared)
        assert not shared.is_closed
        assert len(requests) == 2
    assert shared.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "timeout", "json"])
async def test_model_failures_propagate_and_close_owned_client(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test timeout", request=request)
        if failure == "http":
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, content=b"not json")

    owned = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(client, "create_model_client", lambda: owned)
    expected = {
        "http": httpx.HTTPStatusError,
        "timeout": httpx.ReadTimeout,
        "json": json.JSONDecodeError,
    }
    with pytest.raises(expected[failure]):
        await client.call_model([], [], "test-model", "http://localhost:11434")
    assert len(requests) == 1  # 模型请求不隐式重试。
    assert owned.is_closed


@pytest.mark.asyncio
async def test_model_cancellation_propagates_and_closes_owned_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def respond(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Future[None]()
        raise AssertionError("cancelled request should not resume")

    owned = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(client, "create_model_client", lambda: owned)
    task = asyncio.create_task(client.call_model([], [], "test-model", "http://localhost:11434"))
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert owned.is_closed
