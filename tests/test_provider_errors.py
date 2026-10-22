"""Provider 失败分支：缺可执行文件、超时、非零退出、输出长度异常。"""

import json
import subprocess
from pathlib import Path

import pytest
from packages.crypto.providers import gmssl_cli, openssl_cli

TEST_KEY_ID = "sm2_" + "2" * 32


def test_openssl_missing_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openssl_cli, "OPENSSL_BIN", str(tmp_path / "nope"))
    assert openssl_cli.sha256_digest_file(tmp_path / "f")["error"] == "backend_unavailable"


def test_openssl_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="openssl", timeout=1)

    monkeypatch.setattr(openssl_cli.subprocess, "run", fake_run)
    assert openssl_cli.sha256_digest_file(tmp_path / "f")["error"] == "timeout"


def test_openssl_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(openssl_cli.subprocess, "run", fake_run)
    assert openssl_cli.sha256_digest_file(tmp_path / "f")["error"] == "backend_error"


def test_openssl_nonzero_or_wrong_digest_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Completed:
        returncode = 1
        stdout = b""

    monkeypatch.setattr(openssl_cli.subprocess, "run", lambda *a, **k: _Completed())
    assert openssl_cli.sha256_digest_file(tmp_path / "f")["error"] == "digest_error"

    class _Short:
        returncode = 0
        stdout = b"short"

    monkeypatch.setattr(openssl_cli.subprocess, "run", lambda *a, **k: _Short())
    assert openssl_cli.sha256_digest_file(tmp_path / "f")["error"] == "digest_error"


def _stored_sm2_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "keys"
    directory = root / TEST_KEY_ID
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        json.dumps({"key_id": TEST_KEY_ID, "algorithm": "SM2", "purpose": "sign"}),
        encoding="utf-8",
    )
    private = directory / "private.pem"
    private.write_text("not-a-real-key", encoding="utf-8")
    pass_file = directory / "password.txt"
    pass_file.write_text("local-test-password", encoding="utf-8")
    monkeypatch.setattr(gmssl_cli.keystore, "_KEY_DIR", root)
    return pass_file


def test_gmssl_missing_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stored_sm2_key(tmp_path, monkeypatch)
    monkeypatch.setattr(gmssl_cli, "GMSSL_BIN", tmp_path / "nope")
    result = gmssl_cli.sm2_sign_file(tmp_path / "m", tmp_path / "s", key_id=TEST_KEY_ID)
    assert result["error"] == "backend_or_key_unavailable"


def test_gmssl_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stored_sm2_key(tmp_path, monkeypatch)

    def fake_run(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="gmssl", timeout=1)

    monkeypatch.setattr(gmssl_cli.subprocess, "run", fake_run)
    result = gmssl_cli.sm2_sign_file(tmp_path / "m", tmp_path / "s", key_id=TEST_KEY_ID)
    assert result["error"] == "timeout"


def test_gmssl_rejects_invalid_signer_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stored_sm2_key(tmp_path, monkeypatch)
    result = gmssl_cli.sm2_sign_file(
        tmp_path / "m", tmp_path / "s", key_id=TEST_KEY_ID, signer_id="\x00"
    )
    assert result["error"] == "invalid_input"


def test_gmssl_rejects_invalid_password_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pass_file = _stored_sm2_key(tmp_path, monkeypatch)
    pass_file.write_bytes(b"pass\x00word")
    result = gmssl_cli.sm2_sign_file(tmp_path / "m", tmp_path / "s", key_id=TEST_KEY_ID)
    assert result["error"] == "invalid_password_file"
