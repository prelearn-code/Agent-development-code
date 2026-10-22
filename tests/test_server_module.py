"""Crypto MCP server 模块可导入，并且注册了两个工具包。"""


def test_crypto_server_module_imports() -> None:
    from mcp_integration.server_crypto import server

    assert server.mcp is not None
