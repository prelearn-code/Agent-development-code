"""结构化日志与脱敏。

契约：
  - 日志一律 JSON 行，便于 grep 与后续入库。
  - 密钥、DSN 口令、API Key 必须经过 scrub 后再落盘。
  - MCP server 的日志必须走 stderr —— stdout 是 JSON-RPC 协议通道。
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)"
               r"\s*[=:]\s*([^\s,;\"']+)"),
    re.compile(r"(postgresql(?:\+\w+)?://[^:/@]+:)([^@]+)(@)"),
]


def scrub(text: str) -> str:
    """把疑似密钥替换为 ***。用于日志与错误信息。"""
    out = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 3:
            out = pat.sub(lambda m: f"{m.group(1)}***{m.group(3)}", out)
        else:
            out = pat.sub(lambda m: f"{m.group(1)}=***", out)
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub(record.getMessage()),
        }
        for key in ("run_id", "session_id", "tool_name", "step_index", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", *, stream: Any = None) -> None:
    """配置根 logger。stream 默认 stderr —— 避免污染 stdout 协议通道。"""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


__all__ = ["JsonFormatter", "configure_logging", "get_logger", "scrub"]
