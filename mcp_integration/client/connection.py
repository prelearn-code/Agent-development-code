"""Own the stdio MCP server process and client session lifecycle."""

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_integration.client.bridge import discover_tools

_SERVER_CONFIG_KEYS = (
    "CRYPTO_KEY_ROOT",
    "CRYPTO_DATA_ROOT",
    "GMSSL_BIN",
    "OPENSSL_BIN",
    "CRYPTO_MAX_FILE_BYTES",
    "CRYPTO_TIMEOUT_S",
)


def _server_parameters() -> StdioServerParameters:
    # The MCP SDK inherits only a small safe allowlist; explicitly forward the
    # non-secret Crypto settings so shell overrides reach the child server.
    config_env = {key: os.environ[key] for key in _SERVER_CONFIG_KEYS if key in os.environ}
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_integration.server_crypto.server"],
        env={"PYDEVD_DISABLE_FILE_VALIDATION": "1", **config_env},
    )


@asynccontextmanager
async def connect_tools() -> AsyncIterator[tuple[ClientSession, list[dict[str, Any]]]]:
    param = _server_parameters()
    async with stdio_client(param) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session, await discover_tools(session)
