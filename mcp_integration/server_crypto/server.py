"""Run the SM2 and OpenSSL teaching tools as one stdio Crypto MCP server."""

from mcp.server.mcpserver import MCPServer

from mcp_integration.server_crypto.gmssl_tools.sm_tools import (
    register_tools as register_gmssl_tools,
)
from mcp_integration.server_crypto.openssl_tools.tools import (
    register_tools as register_openssl_tools,
)

mcp = MCPServer("CryptoAssistant")
register_gmssl_tools(mcp)
register_openssl_tools(mcp)


if __name__ == "__main__":
    mcp.run(transport="stdio")
