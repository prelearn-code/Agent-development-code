"""Async Ollama chat requests and the shared HTTP client lifecycle."""

from collections.abc import MutableMapping
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
from packages.llm.context import ContextMessage, build_messages

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
    usage: MutableMapping[str, int] | None = None,
) -> dict[str, Any]:
    """发一次非流式请求，并把四类失败转成有类型的 LLM*Error。

    响应包含完整计数且传入 `usage` 时，回填 `prompt_tokens` / `completion_tokens`
    （来自 Ollama 的 `prompt_eval_count` / `eval_count`），返回值仍是 `message`。
    """
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

    # 先判类型再 .get：响应顶层不是对象时直接按解析失败处理。
    if not isinstance(payload, dict):
        raise LLMParseError(response.text, detail="payload is not an object")

    message = payload.get("message")
    if not isinstance(message, dict):
        raise LLMParseError(response.text, detail="missing message field")

    prompt_tokens = payload.get("prompt_eval_count")
    completion_tokens = payload.get("eval_count")
    if usage is not None and prompt_tokens is not None and completion_tokens is not None:
        usage["prompt_tokens"] = int(prompt_tokens)
        usage["completion_tokens"] = int(completion_tokens)

    return cast(dict[str, Any], message)


async def call_model(
    message: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    base_url: str,
    *,
    client: ModelClient | None = None,
    context: ContextMessage | None = None,
    usage: MutableMapping[str, int] | None = None,
) -> dict[str, Any]:
    """发送原生非流式请求；可复用调用方连接，独立调用时自行创建并关闭。

    `message` 是当前轮的消息；`context` 提供 system / 历史摘要 / 历史轮次。
    传 `context=None` 时只发 `message`，保持旧调用方行为不变。
    `usage` 传字典时回填本次请求的输入/输出 token 数（Ollama 的
    `prompt_eval_count` / `eval_count`）。

    失败时抛 `LLMConnectionError` / `LLMTimeoutError` / `LLMHTTPError` /
    `LLMParseError`，由上层（Loop）转成结构化停止原因。
    """
    request_message = build_messages(context, message)
    settings = get_settings()
    body = {
        "model": model,
        "messages": request_message,
        "tools": tools,
        "stream": False,
        # think 是 /api/chat 的顶层字段，不放进 options；固定 False 才能跨配置比 token。
        "think": settings.LLM_THINK,
        "options": {
            "temperature": 0,
            # num_ctx 必须显式传：不传时 Ollama 用自己的默认窗口（本机实测 4096），
            # 超长时静默从最前面截断，system prompt 和工具规则会被丢掉。
            "num_ctx": settings.LLM_NUM_CTX,
        },
    }
    url = f"{base_url.rstrip('/')}/api/chat"
    timeout_s = settings.LLM_TIMEOUT_S
    if client is not None:
        return await _request_message(client, url, body, timeout_s=timeout_s, usage=usage)
    async with create_model_client() as owned_client:
        return await _request_message(owned_client, url, body, timeout_s=timeout_s, usage=usage)
