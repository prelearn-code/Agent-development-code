"""Async Ollama chat requests and the shared HTTP client lifecycle."""

from typing import Any, cast

import httpx

from packages.core.config import get_settings
from packages.core.errors import (
    LLMConnectionError,
    LLMHTTPError,
    LLMParseError,
    LLMTimeoutError,
)
from packages.core.logging import scrub

type ModelClient = httpx.AsyncClient


def create_model_client() -> ModelClient:
    """每个任务或交互会话创建一次，调用方用 async with 关闭连接池。

    trust_env=False：Ollama 是本机回环服务，不该走 HTTP(S)_PROXY；
    同时避免 httpx 解析 NO_PROXY 里的 `[::1]` 这类条目时抛 InvalidURL。
    """
    return httpx.AsyncClient(
        timeout=get_settings().LLM_TIMEOUT_S,
        follow_redirects=True,
        trust_env=False,
    )


async def _request_message(
    client: ModelClient,
    url: str,
    body: dict[str, Any],
    *,
    timeout_s: float,
) -> dict[str, Any]:
    """发一次非流式请求，并把四类失败转成有类型的 LLM*Error。"""
    try:
        response = await client.post(url, json=body, timeout=timeout_s)
    except httpx.TimeoutException as exc:
        # 先于 ConnectError：ConnectTimeout 同时属于两者
        raise LLMTimeoutError(timeout_s=timeout_s, base_url=url) from exc
    except httpx.ConnectError as exc:
        raise LLMConnectionError(base_url=url, detail=scrub(str(exc))) from exc
    except httpx.HTTPError as exc:
        # ReadError / RemoteProtocolError 等传输层错误
        raise LLMConnectionError(base_url=url, detail=type(exc).__name__) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise LLMHTTPError(exc.response.status_code, exc.response.text) from exc

    try:
        payload = response.json()
    except ValueError as exc:  # json.JSONDecodeError 是 ValueError 子类
        raise LLMParseError(response.text, detail=type(exc).__name__) from exc

    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        raise LLMParseError(response.text, detail="missing message field")
    return cast(dict[str, Any], message)


async def call_model(
    message: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    base_url: str,
    *,
    client: ModelClient | None = None,
) -> dict[str, Any]:
    """发送原生非流式请求；可复用调用方连接，独立调用时自行创建并关闭。

    失败时抛 `LLMConnectionError` / `LLMTimeoutError` / `LLMHTTPError` /
    `LLMParseError`，由上层（Loop）转成结构化停止原因。
    """
    body = {
        "model": model,
        "messages": message,
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0},
    }
    url = f"{base_url.rstrip('/')}/api/chat"
    timeout_s = get_settings().LLM_TIMEOUT_S
    if client is not None:
        return await _request_message(client, url, body, timeout_s=timeout_s)
    async with create_model_client() as owned_client:
        return await _request_message(owned_client, url, body, timeout_s=timeout_s)
