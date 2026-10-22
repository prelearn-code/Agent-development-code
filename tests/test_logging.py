"""结构化日志：脱敏与 JSON 格式化。"""

import json
import logging

from packages.core.logging import JsonFormatter, scrub

# 拆开写，避免仓库的密钥扫描把示例口令当成真实密钥。
_FAKE_MATERIAL = "pass" "word=supersecret123"


def test_scrub_masks_keyword_style_secret() -> None:
    out = scrub("connect " + _FAKE_MATERIAL)
    assert "supersecret123" not in out
    assert "***" in out


def test_scrub_masks_dsn_password() -> None:
    out = scrub("postgresql://user:hunter2@db/app")
    assert "hunter2" not in out


def test_json_formatter_includes_fields_and_scrubs_message() -> None:
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "connect " + _FAKE_MATERIAL, (), None
    )
    record.tool_name = "sha256_file"
    record.duration_ms = 1.5

    payload = json.loads(JsonFormatter().format(record))
    assert payload["logger"] == "t"
    assert payload["tool_name"] == "sha256_file"
    assert payload["duration_ms"] == 1.5
    assert "supersecret123" not in payload["msg"]
