"""The model request uses the configured timeout."""

import io
import urllib.request
from typing import Any

import pytest
from packages.core.config import Settings
from packages.llm import client


def test_model_request_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: Any, *, timeout: int) -> io.BytesIO:
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return io.BytesIO(b'{"message":{"role":"assistant","content":"ok"}}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(client, "get_settings", lambda: Settings.model_construct(LLM_TIMEOUT_S=7))

    assert client.call_model([], [], "test-model", "http://localhost:11434") == {
        "role": "assistant",
        "content": "ok",
    }
    assert seen == {"url": "http://localhost:11434/api/chat", "timeout": 7}
