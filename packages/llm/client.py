"""Async Ollama chat requests and the shared HTTP client lifecycle."""

from typing import Any, cast

import httpx

from packages.core.config import get_settings

type ModelClient = httpx.AsyncClient


def create_model_client() -> ModelClient:
    """每个任务或交互会话创建一次，调用方用 async with 关闭连接池。"""
    return httpx.AsyncClient(timeout=get_settings().LLM_TIMEOUT_S, follow_redirects=True)


async def _request_message(client: ModelClient, url: str, body: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(url, json=body, timeout=get_settings().LLM_TIMEOUT_S)
    response.raise_for_status()
    return cast(dict[str, Any], response.json()["message"])


async def call_model(
    message: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    base_url: str,
    *,
    client: ModelClient | None = None,
) -> dict[str, Any]:
    """发送原生非流式请求；可复用调用方连接，独立调用时自行创建并关闭。"""
    body = {
        "model": model,
        "messages": message,
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0},
    }
    url = f"{base_url.rstrip('/')}/api/chat"
    if client is not None:
        return await _request_message(client, url, body)
    async with create_model_client() as owned_client:
        return await _request_message(owned_client, url, body)
