"""Check the OpenSSL SHA-256 file tool through the provider and MCP transport."""

import hashlib
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_integration.server_crypto.openssl_tools import tools as openssl_tools
from packages.crypto.providers import openssl_cli


def test_sha256_file_matches_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openssl_tools, "_DATA_DIR", tmp_path)
    directory = tmp_path / "file_001"
    directory.mkdir()
    content = b"SHA-256 binary file\x00\xff"
    (directory / "input.bin").write_bytes(content)
    (directory / "signature.der").write_bytes(b"artifact")
    (directory / "ciphertext.der").write_bytes(b"artifact")
    (directory / "decrypted.bin").write_bytes(b"artifact")

    assert openssl_tools.sha256_file("file_001") == {
        "ok": True,
        "algorithm": "SHA-256",
        "digest_hex": hashlib.sha256(content).hexdigest(),
        "file_id": "file_001",
    }


def test_sha256_file_rejects_invalid_input_and_missing_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openssl_tools, "_DATA_DIR", tmp_path)
    directory = tmp_path / "file_001"
    directory.mkdir()
    original = directory / "input.bin"
    original.write_bytes(b"input")
    assert openssl_tools.sha256_file("../file_001")["error"] == "invalid_file"
    (directory / "second.bin").write_bytes(b"second")
    assert openssl_tools.sha256_file("file_001")["error"] == "invalid_file"
    (directory / "second.bin").unlink()
    original.unlink()
    original.symlink_to(tmp_path / "outside.bin")
    assert openssl_tools.sha256_file("file_001")["error"] == "invalid_file"
    original.unlink()
    original.write_bytes(b"input")
    monkeypatch.setattr(openssl_cli, "OPENSSL_BIN", str(tmp_path / "missing-openssl"))
    assert openssl_tools.sha256_file("file_001")["error"] == "backend_unavailable"


@pytest.mark.asyncio
async def test_sha256_file_over_stdio(tmp_path: Path) -> None:
    directory = tmp_path / "file_001"
    directory.mkdir()
    content = b"MCP SHA-256 file\n"
    (directory / "input.bin").write_bytes(content)
    bootstrap = "from mcp_integration.server_crypto.server import mcp; mcp.run(transport='stdio')"
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-B", "-c", bootstrap],
        cwd=str(Path(__file__).resolve().parents[1]),
        env={**os.environ, "CRYPTO_DATA_ROOT": str(tmp_path)},
    )
    with anyio.fail_after(15):
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            sha256 = next(tool for tool in tools.tools if tool.name == "sha256_file")
            assert set(sha256.input_schema["required"]) == {"file_id"}
            assert set(sha256.input_schema["properties"]) == {"file_id"}
            result = await session.call_tool("sha256_file", {"file_id": "file_001"})
            assert not result.is_error and result.structured_content is not None
            assert result.structured_content["digest_hex"] == hashlib.sha256(content).hexdigest()
