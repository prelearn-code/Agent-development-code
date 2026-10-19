"""Existing Ollama chat request used by the minimal Agent."""

import json
import urllib.request
from typing import Any, cast

from packages.core.config import get_settings


def call_model(
    message: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    base_url: str,
) -> dict[str, Any]:
    "把工具与消息发送给ollama指定模型"
    body = json.dumps(
        {
            "model": model,
            "messages": message,
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=get_settings().LLM_TIMEOUT_S) as response:
        return cast(dict[str, Any], json.load(response)["message"])
