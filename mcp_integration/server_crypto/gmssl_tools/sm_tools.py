"""Existing SM2 file tools and their registration on a shared Crypto MCP server."""

import os
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from packages.core.config import get_settings
from packages.crypto import keystore
from packages.crypto.providers import gmssl_cli
from packages.security import resources

_DATA_DIR = get_settings().crypto_data_root
MAX_MESSAGE_BYTES = gmssl_cli.MAX_MESSAGE_BYTES
SM2_ENCRYPT_MAX_BYTES = 255


def sm2_generate_key() -> dict[str, Any]:
    """Generate one teaching SM2 key pair; return the public key and opaque key ID."""
    return keystore.generate_sm2_key()


def _file_directory(file_id: str) -> Path:
    return resources.resolve_file_dir(_DATA_DIR, file_id)


def _message_file(directory: Path, *, max_bytes: int = MAX_MESSAGE_BYTES) -> Path:
    return resources.pick_message_file(directory, max_bytes=max_bytes)


def _sm2_key(key_id: str) -> keystore.KeyBundle | None:
    """SM2 工具只接受 algorithm == "SM2" 的密钥；其他算法在这里被拒。"""
    bundle = resources.resolve_key(key_id)
    if bundle is None or bundle.algorithm != "SM2":
        return None
    return bundle


def sm2_sign_message(file_id: str, key_id: str) -> dict[str, Any]:
    """按 file_id、key_id 对对应文件进行 SM2/SM3 签名。

    密钥位于 keys/<key_id>，文件默认位于 data/<file_id>。
    文件夹内仅放一个待签名的普通文件，大小上限由 CRYPTO_MAX_FILE_BYTES 配置。
    签名保存为同一文件夹内的 signature.der；再次签名覆盖该结果，不应自动重试。
    无需提供文件路径、Base64、私钥、口令或 signer_id。
    """
    if _sm2_key(key_id) is None:
        return {"ok": False, "error": "unknown_key", "message": "未找到对应 key_id 的密钥。"}
    try:
        directory = _file_directory(file_id)
        message_file = _message_file(directory)
    except (OSError, ValueError):
        return {
            "ok": False,
            "error": "invalid_file",
            "message": (
                f"对应 file_id 文件夹须有一个待签名的普通文件，"
                f"大小不超过 {MAX_MESSAGE_BYTES} 字节。"
            ),
        }
    try:
        signature_file = directory / "signature.der"
        if signature_file.is_symlink():
            raise ValueError("signature path is a link")
        with tempfile.TemporaryDirectory(prefix=".sm2-sign-", dir=_DATA_DIR) as pending:
            pending_signature = Path(pending) / "signature.der"
            result = gmssl_cli.sm2_sign_file(message_file, pending_signature, key_id=key_id)
            if not result["ok"]:
                return result
            os.replace(pending_signature, signature_file)
    except (OSError, ValueError):
        return {"ok": False, "error": "signature_save_error", "message": "无法保存签名文件。"}
    return {"ok": True, "file_id": file_id, "key_id": key_id, "signature_file": "signature.der"}


def sm2_verify_signature(file_id: str, key_id: str) -> dict[str, Any]:
    """按 file_id、key_id 验证对应文件夹内的 SM2/SM3 签名。

    使用 keys/<key_id>/public.pem，以及默认 data/<file_id> 内的原文件和 signature.der。
    输入 ID 必须与签名时一致。无需提供公钥、Base64 或签名结果。
    ok 表示是否完成验签，valid 表示签名是否有效。
    """
    bundle = _sm2_key(key_id)
    if bundle is None:
        return {"ok": False, "error": "unknown_key", "message": "未找到对应 key_id 的密钥。"}
    try:
        directory = _file_directory(file_id)
        message_file = _message_file(directory)
        signature_file = directory / "signature.der"
        public_key_file = bundle.public_key
        if signature_file.is_symlink() or public_key_file.is_symlink():
            raise ValueError("linked signature or public key")
        if not 8 <= signature_file.stat().st_size <= 72:
            raise ValueError("invalid signature size")
        with public_key_file.open("r", encoding="ascii") as stream:
            public_key = stream.read(4097)
        if (
            len(public_key) > 4096
            or not public_key.startswith("-----BEGIN PUBLIC KEY-----\n")
            or not public_key.rstrip().endswith("-----END PUBLIC KEY-----")
        ):
            raise ValueError("invalid public key")
    except (OSError, ValueError, UnicodeError):
        return {
            "ok": False,
            "error": "invalid_file",
            "message": "请检查对应的原文件、signature.der 和公钥文件。",
        }
    result = gmssl_cli.sm2_verify_file(message_file, signature_file, public_key_file)
    return {**result, "file_id": file_id, "key_id": key_id}


def sm2_enc(file_id: str, key_id: str) -> dict[str, Any]:
    """Encrypt a file of at most 255 bytes with an SM2 public key.

    Resolve both IDs on the server; publish the binary DER result as ciphertext.der
    only after GmSSL succeeds. Repeated calls replace the previous ciphertext.
    """
    bundle = _sm2_key(key_id)
    if bundle is None:
        return {"ok": False, "error": "unknown_key", "message": "未找到对应 key_id 的密钥。"}

    try:
        directory = _file_directory(file_id)
        message_file = _message_file(directory, max_bytes=SM2_ENCRYPT_MAX_BYTES)
        public_key_file = bundle.public_key
        if public_key_file.is_symlink():
            raise ValueError("linked public key")
        with public_key_file.open("r", encoding="ascii") as stream:
            public_key = stream.read(4097)
        if (
            len(public_key) > 4096
            or not public_key.startswith("-----BEGIN PUBLIC KEY-----\n")
            or not public_key.rstrip().endswith("-----END PUBLIC KEY-----")
        ):
            raise ValueError("invalid public key")
    except (OSError, ValueError, UnicodeError):
        return {
            "ok": False,
            "error": "invalid_file",
            "message": "请检查输入文件（最多 255 字节）和对应的 SM2 公钥文件。",
        }

    try:
        ciphertext_file = directory / "ciphertext.der"
        if ciphertext_file.is_symlink():
            raise ValueError("ciphertext path is a link")
        with tempfile.TemporaryDirectory(prefix=".sm2-encrypt-", dir=_DATA_DIR) as pending:
            pending_ciphertext = Path(pending) / "ciphertext.der"
            result = gmssl_cli.sm2_enc(message_file, pending_ciphertext, public_key=public_key_file)
            if not result["ok"]:
                return result
            os.replace(pending_ciphertext, ciphertext_file)
    except (OSError, ValueError):
        return {"ok": False, "error": "ciphertext_save_error", "message": "无法保存密文文件。"}
    return {"ok": True, "file_id": file_id, "key_id": key_id, "ciphertext_file": "ciphertext.der"}


def sm2_dec(file_id: str, key_id: str) -> dict[str, Any]:
    """Decrypt ciphertext.der with the selected SM2 key into a local file.

    The plaintext stays on the server as decrypted.bin and is never returned
    through MCP. A failed attempt does not replace an earlier result.
    """
    if _sm2_key(key_id) is None:
        return {"ok": False, "error": "unknown_key", "message": "未找到对应 key_id 的密钥。"}
    try:
        directory = _file_directory(file_id)
        ciphertext_file = directory / "ciphertext.der"
        if ciphertext_file.is_symlink() or not ciphertext_file.is_file():
            raise ValueError("invalid ciphertext file")
        if not 8 <= ciphertext_file.stat().st_size <= 1024:
            raise ValueError("invalid ciphertext size")
        with ciphertext_file.open("rb") as stream:
            if stream.read(1) != b"\x30":
                raise ValueError("invalid DER ciphertext")
    except (OSError, ValueError):
        return {
            "ok": False,
            "error": "invalid_file",
            "message": "请检查对应 file_id 目录中的 ciphertext.der 密文文件。",
        }

    try:
        plaintext_file = directory / "decrypted.bin"
        if plaintext_file.is_symlink():
            raise ValueError("plaintext path is a link")
        with tempfile.TemporaryDirectory(prefix=".sm2-decrypt-", dir=_DATA_DIR) as pending:
            pending_plaintext = Path(pending) / "decrypted.bin"
            pending_plaintext.touch(mode=0o600, exist_ok=False)
            result = gmssl_cli.sm2_dec(ciphertext_file, pending_plaintext, key_id=key_id)
            if not result["ok"]:
                return result
            os.replace(pending_plaintext, plaintext_file)
    except (OSError, ValueError):
        return {"ok": False, "error": "plaintext_save_error", "message": "无法保存解密文件。"}
    return {"ok": True, "file_id": file_id, "key_id": key_id, "plaintext_file": "decrypted.bin"}


def register_tools(mcp: MCPServer) -> None:
    """02–04 段只暴露只读工具；写操作 06 段再开。

    写工具的函数与单元测试保留，只是不出现在 tools/list 里——模型看不见就
    不会去猜。恢复注册时连同风险策略一起在 06 段处理。
    """
    mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False))(
        sm2_verify_signature
    )
