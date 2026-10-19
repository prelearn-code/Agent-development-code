"""OpenSSL MCP tools for server-resolved teaching files."""

import re
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from packages.core.config import get_settings
from packages.crypto.providers import openssl_cli

_DATA_DIR = get_settings().crypto_data_root
_OUTPUT_FILES = {"signature.der", "ciphertext.der", "decrypted.bin"}


def sha256_file(file_id: str) -> dict[str, Any]:
    """Calculate SHA-256 for the sole original file in data/<file_id> by default.

    Only a server-side file ID is accepted; file contents and paths are not
    passed to the model. The result contains the hexadecimal digest.
    """
    try:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", file_id) is None:
            raise ValueError("invalid file ID")
        directory = _DATA_DIR / file_id
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("file directory unavailable")
        files = [path for path in directory.iterdir() if path.name not in _OUTPUT_FILES]
        if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
            raise ValueError("exactly one original file required")
        input_file = files[0]
        if input_file.stat().st_size > openssl_cli.MAX_MESSAGE_BYTES:
            raise ValueError("message too large")
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
