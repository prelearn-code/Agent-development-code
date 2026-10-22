"""High-level MCP Client discovery and connection cleanup."""

from unittest.mock import AsyncMock, patch

import anyio
import pytest
from mcp import Client
from mcp_integration.client import connection


@pytest.mark.asyncio
async def test_connect_tools_discovers_read_only_tools_over_stdio() -> None:
    with anyio.fail_after(15):
        async with connection.connect_tools() as (session, tools):
            assert isinstance(session, Client)
            assert {tool["function"]["name"] for tool in tools} == {
                "sha256_file",
                "sm2_verify_signature",
            }


@pytest.mark.asyncio
async def test_connect_tools_closes_client_when_discovery_fails() -> None:
    managed = AsyncMock()
    with (
        patch.object(connection, "Client", return_value=managed),
        patch.object(connection, "discover_tools", side_effect=RuntimeError("discovery failed")),
        pytest.raises(RuntimeError, match="discovery failed"),
    ):
        async with connection.connect_tools():
            raise AssertionError("discovery must succeed before yielding")
    managed.__aexit__.assert_awaited_once()
