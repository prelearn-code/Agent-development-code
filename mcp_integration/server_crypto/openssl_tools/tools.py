"""OpenSSL MCP tools for server-resolved teaching files."""

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from packages.core.config import get_settings
from packages.core.resource_schema import FileId
from packages.crypto.providers import openssl_cli
from packages.security import resources

_DATA_DIR = get_settings().crypto_data_root


def sha256_file(file_id: FileId) -> dict[str, Any]:
    """Calculate SHA-256 for the sole original file in data/<file_id> by default.

    Only a server-side file ID is accepted; file contents and paths are not
    passed to the model. The result contains the hexadecimal digest.
    """
    try:
        input_file = resources.resolve_message_file(
            _DATA_DIR, file_id, max_bytes=openssl_cli.MAX_MESSAGE_BYTES
        )
    except (OSError, ValueError):
        return {
            "ok": False,
            "error": "invalid_file",
            "message": (
                f"对应 file_id 文件夹须有一个不超过 {openssl_cli.MAX_MESSAGE_BYTES} "
                "字节的普通原始文件。"
            ),
        }

    result = openssl_cli.sha256_digest_file(input_file)
    return {**result, "file_id": file_id}


def register_tools(mcp: MCPServer) -> None:
    """Publish OpenSSL tools on the shared Crypto MCP server."""
    mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False))(sha256_file)
