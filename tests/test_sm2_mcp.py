"""用临时 GmSSL 签名及 OpenSSL 交叉验签，验证工具和真实 MCP 调用。"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_integration.server_crypto.gmssl_tools import sm_tools
from mcp_integration.server_crypto.gmssl_tools.sm_tools import sm2_generate_key
from packages.crypto import keystore
from packages.crypto.providers import gmssl_cli
from packages.crypto.providers.gmssl_cli import sm2_sign_file, sm2_verify_file

GMSSL_BIN = gmssl_cli.GMSSL_BIN


@pytest.fixture
def signed_message(tmp_path: Path) -> dict[str, Path]:
    openssl = shutil.which("openssl")
    if openssl is None or not GMSSL_BIN.is_file():
        pytest.skip("需要本地 OpenSSL 和 GmSSL")
    key = tmp_path / "test-key.pem"
    public_key = tmp_path / "public.pem"
    message = tmp_path / "message.bin"
    signature = tmp_path / "signature.der"
    message.write_bytes(b"SM2 MCP public test message")
    (tmp_path / "password.txt").write_text("local-test-only\n")
    commands = [
        [
            str(GMSSL_BIN),
            "sm2keygen",
            "-pass",
            "local-test-only",
            "-out",
            str(key),
            "-pubout",
            str(public_key),
        ],
        [
            str(GMSSL_BIN),
            "sm2sign",
            "-key",
            str(key),
            "-pass",
            "local-test-only",
            "-in",
            str(message),
            "-out",
            str(signature),
        ],
        [
            openssl,
            "pkeyutl",
            "-verify",
            "-pubin",
            "-rawin",
            "-digest",
            "sm3",
            "-pkeyopt",
            "distid:1234567812345678",
            "-inkey",
            str(public_key),
            "-in",
            str(message),
            "-sigfile",
            str(signature),
        ],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, timeout=10)
    return {
        "private_key": key,
        "public_key": public_key,
        "message": message,
        "signature": signature,
        "password": tmp_path / "password.txt",
    }


def test_valid_signature(signed_message: dict[str, Path]) -> None:
    assert sm2_verify_file(
        signed_message["message"], signed_message["signature"], signed_message["public_key"]
    ) == {
        "ok": True,
        "valid": True,
        "algorithm": "SM2/SM3",
    }


def test_changed_message_not_verified(signed_message: dict[str, Path]) -> None:
    signed_message["message"].write_bytes(b"different message")
    result = sm2_verify_file(
        signed_message["message"], signed_message["signature"], signed_message["public_key"]
    )
    # 本地 GmSSL 将签名不匹配也报告为 inner error，不能伪装成成功执行。
    assert result["ok"] is False
    assert result["error"] == "verification_error"


def test_invalid_signature(signed_message: dict[str, Path]) -> None:
    signed_message["signature"].write_bytes(b"not-DER!")
    result = sm2_verify_file(
        signed_message["message"], signed_message["signature"], signed_message["public_key"]
    )
    assert result["error"] == "verification_error"


def test_sign_then_verify(
    signed_message: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        keystore,
        "SM2_SIGNING_KEYS",
        {
            "default": (signed_message["private_key"], signed_message["password"]),
        },
    )
    signature = tmp_path / "tool-signature.der"
    result = sm2_sign_file(signed_message["message"], signature, signer_id="test-user")
    assert result["ok"] is True
    assert "private_key" not in result and "password" not in result
    verification = sm2_verify_file(
        signed_message["message"],
        signature,
        signed_message["public_key"],
        signer_id="test-user",
    )
    assert verification["valid"] is True
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-rawin",
            "-digest",
            "sm3",
            "-pkeyopt",
            "distid:test-user",
            "-inkey",
            str(tmp_path / "public.pem"),
            "-in",
            str(tmp_path / "message.bin"),
            "-sigfile",
            str(signature),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )


def test_unknown_signing_key(tmp_path: Path) -> None:
    assert (
        sm2_sign_file(tmp_path / "message", tmp_path / "signature", key_id="not-configured")[
            "error"
        ]
        == "unknown_key"
    )


def test_sign_rejects_linked_key_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    private = tmp_path / "private.pem"
    private.write_text("test key")
    pass_file = tmp_path / "password.txt"
    pass_file.write_text("test password")
    private_link = tmp_path / "private-link.pem"
    private_link.symlink_to(private)
    pass_link = tmp_path / "password-link.txt"
    pass_link.symlink_to(pass_file)

    monkeypatch.setattr(keystore, "SM2_SIGNING_KEYS", {"default": (private_link, pass_file)})
    assert sm2_sign_file(tmp_path / "message", tmp_path / "signature")["error"] == "key_unavailable"

    monkeypatch.setattr(keystore, "SM2_SIGNING_KEYS", {"default": (private, pass_link)})
    assert (
        sm2_sign_file(tmp_path / "message", tmp_path / "signature")["error"]
        == "invalid_password_file"
    )


def test_wrong_key_password(
    signed_message: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "password.txt").write_text("incorrect-test-password")
    monkeypatch.setattr(
        keystore,
        "SM2_SIGNING_KEYS",
        {
            "default": (signed_message["private_key"], signed_message["password"]),
        },
    )
    assert (
        sm2_sign_file(signed_message["message"], tmp_path / "bad-signature.der")["error"]
        == "signing_error"
    )


def test_generate_and_use_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not GMSSL_BIN.is_file():
        pytest.skip("需要本地 GmSSL")
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path)
    first = sm2_generate_key()
    second = sm2_generate_key()
    assert first["ok"] is True and second["ok"] is True
    assert first["key_id"] != second["key_id"]
    assert first["public_key_pem"] != second["public_key_pem"]
    assert "private_key_pem" not in first and "password" not in first
    directory = tmp_path / first["key_id"]
    assert directory.stat().st_mode & 0o777 == 0o700
    for filename in ("private.pem", "password.txt", "public.pem", "metadata.json"):
        assert (directory / filename).stat().st_mode & 0o777 == 0o600
    metadata = json.loads((directory / "metadata.json").read_text())
    assert metadata["key_id"] == first["key_id"]
    # 模拟重启后没有动态内存注册，仍可按服务端 ID 找到保存的密钥。
    monkeypatch.setattr(keystore, "SM2_SIGNING_KEYS", {})
    message = tmp_path / "message.bin"
    signature = tmp_path / "signature.der"
    message.write_bytes(b"generated key test")
    signed = sm2_sign_file(message, signature, key_id=first["key_id"])
    assert signed["ok"] is True
    assert (
        sm2_verify_file(
            message,
            signature,
            directory / "public.pem",
        )["valid"]
        is True
    )


def test_flat_key_lookup_checks_algorithm_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path / "keys")
    monkeypatch.setattr(keystore, "SM2_SIGNING_KEYS", {})
    key_id = "sm2_" + "a" * 32
    directory = tmp_path / "keys" / key_id
    directory.mkdir(parents=True)
    metadata_file = directory / "metadata.json"
    metadata_file.write_text(json.dumps({"key_id": key_id, "algorithm": "RSA"}))
    assert keystore.find_sm2_key(key_id) is None

    metadata_file.write_text(json.dumps({"key_id": key_id, "algorithm": "SM2"}))
    assert keystore.find_sm2_key(key_id) == (
        directory / "private.pem",
        directory / "password.txt",
    )


def test_generate_missing_backend_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path)
    monkeypatch.setattr(gmssl_cli, "GMSSL_BIN", tmp_path / "no-gmssl")
    assert sm2_generate_key()["error"] == "backend_unavailable"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_sm2_over_stdio(signed_message: dict[str, Path], tmp_path: Path) -> None:
    data_dir = tmp_path / "data" / "file_001"
    data_dir.mkdir(parents=True)
    (data_dir / "message.bin").write_bytes(signed_message["message"].read_bytes())
    bootstrap = (
        "from pathlib import Path; from packages.crypto import keystore; "
        "from mcp_integration.server_crypto.gmssl_tools import sm_tools; "
        "from mcp_integration.server_crypto.server import mcp; "
        f"keystore._KEY_DIR = Path({str(tmp_path / 'keys')!r}); "
        f"sm_tools._DATA_DIR = Path({str(tmp_path / 'data')!r}); "
        "mcp.run(transport='stdio')"
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-B", "-c", bootstrap],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    with anyio.fail_after(15):
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {
                "sm2_verify_signature",
                "sm2_sign_message",
                "sm2_generate_key",
                "sm2_enc",
                "sm2_dec",
            } <= {tool.name for tool in tools.tools}
            for tool in tools.tools:
                if tool.name in {"sm2_sign_message", "sm2_verify_signature", "sm2_enc", "sm2_dec"}:
                    assert set(tool.input_schema["required"]) == {"file_id", "key_id"}
                    assert set(tool.input_schema["properties"]) == {"file_id", "key_id"}
            generated = await session.call_tool("sm2_generate_key", {})
            assert not generated.is_error and generated.structured_content is not None
            key = generated.structured_content
            assert key["ok"] is True
            assert (tmp_path / "keys" / key["key_id"] / "private.pem").is_file()
            arguments = {"file_id": "file_001", "key_id": key["key_id"]}
            signed = await session.call_tool("sm2_sign_message", arguments)
            assert not signed.is_error and signed.structured_content is not None
            assert signed.structured_content["ok"] is True
            assert (data_dir / "signature.der").is_file()
            verified = await session.call_tool("sm2_verify_signature", arguments)
            assert verified.structured_content is not None
            assert verified.structured_content["valid"] is True
            encrypted = await session.call_tool("sm2_enc", arguments)
            assert not encrypted.is_error and encrypted.structured_content is not None
            assert encrypted.structured_content["ciphertext_file"] == "ciphertext.der"
            assert (data_dir / "ciphertext.der").is_file()
            decrypted = await session.call_tool("sm2_dec", arguments)
            assert not decrypted.is_error and decrypted.structured_content is not None
            assert decrypted.structured_content["plaintext_file"] == "decrypted.bin"
            assert "plaintext" not in decrypted.structured_content
            assert (data_dir / "decrypted.bin").read_bytes() == signed_message[
                "message"
            ].read_bytes()


def test_file_sign_verify_and_openssl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not GMSSL_BIN.is_file() or shutil.which("openssl") is None:
        pytest.skip("需要本地 OpenSSL 和 GmSSL")
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path / "keys")
    monkeypatch.setattr(sm_tools, "_DATA_DIR", tmp_path / "data")
    key = sm2_generate_key()
    assert key["ok"] is True
    directory = tmp_path / "data" / "file_001"
    directory.mkdir(parents=True)
    original = directory / "example.txt"
    original.write_bytes("中文文件签名测试\n".encode() + b"\x00\xff")
    arguments = {"file_id": "file_001", "key_id": key["key_id"]}
    signed = sm_tools.sm2_sign_message(**arguments)
    assert signed["ok"] is True
    assert set(signed) == {"ok", "file_id", "key_id", "signature_file"}
    assert sm_tools.sm2_verify_signature(**arguments)["valid"] is True
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-rawin",
            "-digest",
            "sm3",
            "-pkeyopt",
            "distid:1234567812345678",
            "-inkey",
            str(tmp_path / "keys" / key["key_id"] / "public.pem"),
            "-in",
            str(original),
            "-sigfile",
            str(directory / "signature.der"),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    # 模拟重启：移除内存配置，仍可按 ID 从指定目录读取。
    monkeypatch.setattr(keystore, "SM2_SIGNING_KEYS", {})
    assert sm_tools.sm2_verify_signature(**arguments)["valid"] is True
    original.write_bytes(b"changed")
    assert not sm_tools.sm2_verify_signature(**arguments).get("valid", False)


def test_failed_resign_preserves_existing_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not GMSSL_BIN.is_file():
        pytest.skip("需要本地 GmSSL")
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path / "keys")
    monkeypatch.setattr(sm_tools, "_DATA_DIR", tmp_path / "data")
    key = sm2_generate_key()
    assert key["ok"] is True
    directory = tmp_path / "data" / "file_001"
    directory.mkdir(parents=True)
    (directory / "message.bin").write_bytes(b"sign this file")
    arguments = {"file_id": "file_001", "key_id": key["key_id"]}
    assert sm_tools.sm2_sign_message(**arguments)["ok"] is True
    signature_file = directory / "signature.der"
    original_signature = signature_file.read_bytes()

    (tmp_path / "keys" / key["key_id"] / "password.txt").write_text("wrong password")
    assert sm_tools.sm2_sign_message(**arguments)["error"] == "signing_error"
    assert signature_file.read_bytes() == original_signature


def test_sm2_encrypt_file_roundtrip(
    signed_message: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sm_tools, "_DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        keystore,
        "SM2_SIGNING_KEYS",
        {"default": (signed_message["private_key"], signed_message["password"])},
    )
    directory = tmp_path / "data" / "file_001"
    directory.mkdir(parents=True)
    original = directory / "message.bin"
    original.write_bytes(b"SM2 short binary message\x00\xff")

    encrypted = sm_tools.sm2_enc("file_001", "default")
    assert encrypted == {
        "ok": True,
        "file_id": "file_001",
        "key_id": "default",
        "ciphertext_file": "ciphertext.der",
    }
    ciphertext = directory / "ciphertext.der"
    assert ciphertext.read_bytes() != original.read_bytes()
    decrypted = tmp_path / "decrypted.bin"
    subprocess.run(
        [
            str(GMSSL_BIN),
            "sm2decrypt",
            "-key",
            str(signed_message["private_key"]),
            "-pass",
            "local-test-only",
            "-in",
            str(ciphertext),
            "-out",
            str(decrypted),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    assert decrypted.read_bytes() == original.read_bytes()
    tool_decrypted = sm_tools.sm2_dec("file_001", "default")
    assert tool_decrypted == {
        "ok": True,
        "file_id": "file_001",
        "key_id": "default",
        "plaintext_file": "decrypted.bin",
    }
    assert (directory / "decrypted.bin").read_bytes() == original.read_bytes()
    assert (directory / "decrypted.bin").stat().st_mode & 0o777 == 0o600
    # The generated ciphertext is an output artifact, not a second input file.
    assert sm_tools.sm2_sign_message("file_001", "default")["ok"] is True


def test_sm2_encrypt_rejects_large_input_and_preserves_old_ciphertext(
    signed_message: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sm_tools, "_DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        keystore,
        "SM2_SIGNING_KEYS",
        {"default": (signed_message["private_key"], signed_message["password"])},
    )
    directory = tmp_path / "data" / "file_001"
    directory.mkdir(parents=True)
    original = directory / "message.bin"
    original.write_bytes(b"short")
    assert sm_tools.sm2_enc("file_001", "default")["ok"] is True
    ciphertext = directory / "ciphertext.der"
    previous = ciphertext.read_bytes()

    original.write_bytes(b"x" * 256)
    assert sm_tools.sm2_enc("file_001", "default")["error"] == "invalid_file"
    assert ciphertext.read_bytes() == previous
    original.write_bytes(b"short again")
    monkeypatch.setattr(gmssl_cli, "GMSSL_BIN", tmp_path / "missing-gmssl")
    assert sm_tools.sm2_enc("file_001", "default")["error"] == "backend_unavailable"
    assert ciphertext.read_bytes() == previous


def test_sm2_decrypt_failure_preserves_existing_plaintext(
    signed_message: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sm_tools, "_DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        keystore,
        "SM2_SIGNING_KEYS",
        {"default": (signed_message["private_key"], signed_message["password"])},
    )
    directory = tmp_path / "data" / "file_001"
    directory.mkdir(parents=True)
    (directory / "message.bin").write_bytes(b"private test message")
    assert sm_tools.sm2_enc("file_001", "default")["ok"] is True
    assert sm_tools.sm2_dec("file_001", "default")["ok"] is True
    plaintext_file = directory / "decrypted.bin"
    previous = plaintext_file.read_bytes()

    signed_message["password"].write_text("incorrect-test-password")
    assert sm_tools.sm2_dec("file_001", "default")["error"] == "decryption_error"
    assert plaintext_file.read_bytes() == previous

    ciphertext_file = directory / "ciphertext.der"
    ciphertext_file.write_bytes(b"invalid")
    assert sm_tools.sm2_dec("file_001", "default")["error"] == "invalid_file"
    assert plaintext_file.read_bytes() == previous


def test_missing_file_and_signature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not GMSSL_BIN.is_file():
        pytest.skip("需要本地 GmSSL")
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path / "keys")
    monkeypatch.setattr(sm_tools, "_DATA_DIR", tmp_path / "data")
    key = sm2_generate_key()
    assert key["ok"] is True
    arguments = {"file_id": "file_001", "key_id": key["key_id"]}
    assert sm_tools.sm2_sign_message(**arguments)["error"] == "invalid_file"
    directory = tmp_path / "data" / "file_001"
    directory.mkdir(parents=True)
    (directory / "input.txt").write_text("test")
    assert sm_tools.sm2_verify_signature(**arguments)["error"] == "invalid_file"
    (directory / "second.txt").write_text("second")
    assert sm_tools.sm2_sign_message(**arguments)["error"] == "invalid_file"


def test_unknown_file_signing_key() -> None:
    assert sm_tools.sm2_sign_message("file_001", "not-configured")["error"] == "unknown_key"
    assert sm_tools.sm2_verify_signature("file_001", "not-configured")["error"] == "unknown_key"
    assert sm_tools.sm2_dec("file_001", "not-configured")["error"] == "unknown_key"
