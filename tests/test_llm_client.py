"""模型客户端：四类失败分类与成功路径（httpx.MockTransport，无网络）。"""

import httpx
import pytest
from packages.core.errors import (
    LLMConnectionError,
    LLMHTTPError,
    LLMParseError,
    LLMTimeoutError,
)
from packages.llm import client as client_module
from packages.llm.client import call_model

# 拆开写，避免仓库的密钥扫描把示例口令当成真实密钥。
_FAKE_MATERIAL = "pass" "word=supersecret123"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_success_returns_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "ok"}}
        )

    async with _client(handler) as client:
        result = await call_model([], [], "model", "http://127.0.0.1:1", client=client)
    assert result == {"role": "assistant", "content": "ok"}


@pytest.mark.asyncio
async def test_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with _client(handler) as client:
        with pytest.raises(LLMConnectionError) as info:
            await call_model([], [], "model", "http://127.0.0.1:1", client=client)
    assert info.value.base_url == "http://127.0.0.1:1/api/chat"
    assert info.value.reason == "llm_connection_error"


@pytest.mark.asyncio
async def test_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    async with _client(handler) as client:
        with pytest.raises(LLMTimeoutError) as info:
            await call_model([], [], "model", "http://127.0.0.1:1", client=client)
    assert info.value.timeout_s > 0
    assert info.value.reason == "llm_timeout"


@pytest.mark.asyncio
async def test_http_error_carries_status_and_scrubbed_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom " + _FAKE_MATERIAL)

    async with _client(handler) as client:
        with pytest.raises(LLMHTTPError) as info:
            await call_model([], [], "model", "http://127.0.0.1:1", client=client)
    assert info.value.status_code == 500
    assert info.value.reason == "llm_http_500"
    assert "supersecret123" not in info.value.response_text
    assert "status=500" in str(info.value)


@pytest.mark.asyncio
async def test_non_json_response_is_parse_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    async with _client(handler) as client:
        with pytest.raises(LLMParseError) as info:
            await call_model([], [], "model", "http://127.0.0.1:1", client=client)
    assert info.value.reason == "llm_parse_error"
    assert "JSON" in info.value.context["detail"]


@pytest.mark.asyncio
async def test_missing_message_field_is_parse_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"foo": 1})

    async with _client(handler) as client:
        with pytest.raises(LLMParseError) as info:
            await call_model([], [], "model", "http://127.0.0.1:1", client=client)
    assert info.value.context["detail"] == "missing message field"


@pytest.mark.asyncio
async def test_call_model_without_client_creates_and_closes_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    owned = _client(handler)
    monkeypatch.setattr(client_module, "create_model_client", lambda: owned)

    result = await call_model([], [], "model", "http://127.0.0.1:1")

    assert result["content"] == "ok"
    assert owned.is_closed
