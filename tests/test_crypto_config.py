"""The crypto modules use one system configuration regardless of launch directory."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp_integration.client.connection import _server_parameters
from packages.core.config import Settings
from packages.crypto import keystore


def test_crypto_config_reaches_mcp_and_provider_modules(tmp_path: Path) -> None:
    if not Path("/bin/openssl").is_file():
        pytest.skip("OpenSSL binary is unavailable")
    repo = Path(__file__).resolve().parents[1]
    file_dir = tmp_path / "files" / "file_001"
    file_dir.mkdir(parents=True)
    content = b"configured file root\n"
    (file_dir / "input.bin").write_bytes(content)
    (tmp_path / "openssl").symlink_to("/bin/openssl")
    script = """
import json
from mcp_integration.server_crypto.gmssl_tools import sm_tools
from mcp_integration.server_crypto.openssl_tools import tools as openssl_tools
from packages.crypto import keystore
from packages.crypto.providers import gmssl_cli, openssl_cli

print(json.dumps({
    "sha256": openssl_tools.sha256_file("file_001"),
    "key_root": str(keystore._KEY_DIR),
    "gmssl_data_root": str(sm_tools._DATA_DIR),
    "openssl_data_root": str(openssl_tools._DATA_DIR),
    "gmssl_bin": str(gmssl_cli.GMSSL_BIN),
    "openssl_bin": str(openssl_cli.OPENSSL_BIN),
    "gmssl_max_bytes": gmssl_cli.MAX_MESSAGE_BYTES,
    "openssl_max_bytes": openssl_cli.MAX_MESSAGE_BYTES,
    "gmssl_timeout": gmssl_cli.TIMEOUT_S,
    "openssl_timeout": openssl_cli.TIMEOUT_S,
}))
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(repo),
        "CRYPTO_KEY_ROOT": "test-keys",
        "CRYPTO_DATA_ROOT": str(tmp_path / "files"),
        "GMSSL_BIN": "bin/gmssl",
        "OPENSSL_BIN": str(tmp_path / "openssl"),
        "CRYPTO_MAX_FILE_BYTES": "4096",
        "CRYPTO_TIMEOUT_S": "3",
    }
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert json.loads(completed.stdout) == {
        "sha256": {
            "ok": True,
            "algorithm": "SHA-256",
            "digest_hex": hashlib.sha256(content).hexdigest(),
            "file_id": "file_001",
        },
        "key_root": str(repo / "test-keys"),
        "gmssl_data_root": str(tmp_path / "files"),
        "openssl_data_root": str(tmp_path / "files"),
        "gmssl_bin": str(repo / "bin/gmssl"),
        "openssl_bin": str(tmp_path / "openssl"),
        "gmssl_max_bytes": 4096,
        "openssl_max_bytes": 4096,
        "gmssl_timeout": 3,
        "openssl_timeout": 3,
    }


def test_crypto_defaults_match_example_and_flat_file_layout() -> None:
    repo = Path(__file__).resolve().parents[1]
    example = dict(
        line.split("=", 1)
        for line in (repo / ".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    settings = Settings.model_construct()
    for key in (
        "CRYPTO_KEY_ROOT",
        "CRYPTO_DATA_ROOT",
        "GMSSL_BIN",
        "OPENSSL_BIN",
        "CRYPTO_MAX_FILE_BYTES",
        "CRYPTO_TIMEOUT_S",
    ):
        assert example[key] == str(getattr(settings, key))
    assert settings.crypto_data_root == repo / "data"


def test_crypto_environment_reaches_mcp_child(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRYPTO_DATA_ROOT", "/tmp/custom-crypto-files")
    monkeypatch.setenv("GMSSL_BIN", "/tmp/custom-gmssl")
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-forward")
    env = _server_parameters().env
    assert env is not None
    assert env["CRYPTO_DATA_ROOT"] == "/tmp/custom-crypto-files"
    assert env["GMSSL_BIN"] == "/tmp/custom-gmssl"
    assert "UNRELATED_SECRET" not in env


def test_existing_key_root_permissions_are_not_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "shared"
    root.mkdir()
    root.chmod(0o755)
    monkeypatch.setattr(keystore, "_KEY_DIR", root)

    assert keystore.generate_sm2_key()["error"] == "key_storage_error"
    assert root.stat().st_mode & 0o777 == 0o755
    assert list(root.iterdir()) == []
