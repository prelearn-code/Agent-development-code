"""Fixed GmSSL executable calls for SM2 teaching operations."""

import subprocess
from pathlib import Path
from typing import Any

from packages.core.config import get_settings
from packages.crypto import keystore

_SETTINGS = get_settings()
GMSSL_BIN = _SETTINGS.gmssl_bin
MAX_MESSAGE_BYTES = _SETTINGS.CRYPTO_MAX_FILE_BYTES
TIMEOUT_S = _SETTINGS.CRYPTO_TIMEOUT_S


def generate_keypair(
    private_key: Path, public_key: Path, passphrase: str
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            str(GMSSL_BIN),
            "sm2keygen",
            "-pass",
            passphrase,
            "-out",
            str(private_key),
            "-pubout",
            str(public_key),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=TIMEOUT_S,
        check=False,
    )


def sm2_sign_file(
    message_file: Path,
    signature_file: Path,
    *,
    key_id: str = "default",
    signer_id: str = "1234567812345678",
) -> dict[str, Any]:
    """Sign a server-resolved file with GmSSL -in/-out; never expose key material."""
    key_files = keystore.find_sm2_key(key_id)
    if key_files is None:
        return {"ok": False, "error": "unknown_key", "message": "未配置该密钥标识。"}
    try:
        id_bytes = signer_id.encode("utf-8")
        if not 1 <= len(id_bytes) <= 8191 or "\x00" in signer_id:
            raise ValueError("invalid signer ID")
    except (ValueError, UnicodeError):
        return {"ok": False, "error": "invalid_input", "message": "请检查用户标识。"}

    private_key_file, password_file = key_files
    try:
        if private_key_file.is_symlink() or not private_key_file.is_file():
            return {"ok": False, "error": "key_unavailable", "message": "未配置私钥文件。"}
        if password_file.is_symlink():
            return {"ok": False, "error": "invalid_password_file", "message": "口令文件无效。"}
        with password_file.open("rb") as password_stream:
            password_bytes = password_stream.read(1025)
        passphrase = password_bytes.decode("utf-8").removesuffix("\n").removesuffix("\r")
        if not passphrase or len(password_bytes) > 1024 or "\x00" in passphrase:
            return {"ok": False, "error": "invalid_password_file", "message": "口令文件无效。"}
        # GmSSL -pass exposes the teaching passphrase in the child process argv.
        # Never log arguments, raw stderr, or exceptions containing the command.
        completed = subprocess.run(
            [
                str(GMSSL_BIN),
                "sm2sign",
                "-key",
                str(private_key_file),
                "-pass",
                passphrase,
                "-id",
                signer_id,
                "-in",
                str(message_file),
                "-out",
                str(signature_file),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "backend_or_key_unavailable",
            "message": "GmSSL 或口令文件不存在。",
        }
    except UnicodeError:
        return {
            "ok": False,
            "error": "invalid_password_file",
            "message": "口令文件需要 UTF-8 编码。",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "message": "GmSSL 签名超时。"}
    except OSError:
        return {"ok": False, "error": "backend_error", "message": "无法执行 GmSSL 签名。"}

    try:
        valid_signature = 8 <= signature_file.stat().st_size <= 72
    except OSError:
        valid_signature = False
    if completed.returncode != 0 or not valid_signature:
        return {
            "ok": False,
            "error": "signing_error",
            "message": "签名失败，请检查私钥格式和口令。",
        }
    return {"ok": True, "algorithm": "SM2/SM3", "key_id": key_id, "signer_id": signer_id}


def sm2_verify_file(
    message_file: Path,
    signature_file: Path,
    public_key_file: Path,
    *,
    signer_id: str = "1234567812345678",
) -> dict[str, Any]:
    """Verify a server-resolved file and DER signature with GmSSL -in/-sig."""
    try:
        id_bytes = signer_id.encode("utf-8")
        if not 1 <= len(id_bytes) <= 8191 or "\x00" in signer_id:
            raise ValueError("invalid signer ID")
    except (ValueError, UnicodeError):
        return {"ok": False, "error": "invalid_input", "message": "请检查用户标识。"}

    try:
        completed = subprocess.run(
            [
                str(GMSSL_BIN),
                "sm2verify",
                "-pubkey",
                str(public_key_file),
                "-id",
                signer_id,
                "-sig",
                str(signature_file),
                "-in",
                str(message_file),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "backend_unavailable", "message": "未找到本地 GmSSL。"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "message": "GmSSL 验签超时。"}
    except OSError:
        return {"ok": False, "error": "backend_error", "message": "无法执行 GmSSL 验签。"}

    result = completed.stdout.strip()
    if completed.returncode == 0 and result == b"verify : success":
        return {"ok": True, "valid": True, "algorithm": "SM2/SM3"}
    if completed.returncode == 1 and result == b"verify : failure":
        return {"ok": True, "valid": False, "algorithm": "SM2/SM3"}
    return {
        "ok": False,
        "error": "verification_error",
        "message": "验签未通过：签名不匹配，或公钥类型、DER 签名格式无效。",
    }


def sm2_enc(input_file: Path, out_file: Path, *, public_key: Path) -> dict[str, Any]:
    """Encrypt one short file with a server-selected SM2 public key."""
    try:
        completed = subprocess.run(
            [
                str(GMSSL_BIN),
                "sm2encrypt",
                "-pubkey",
                str(public_key),
                "-in",
                str(input_file),
                "-out",
                str(out_file),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "backend_unavailable", "message": "未找到本地 GmSSL。"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "message": "GmSSL 加密超时。"}
    except OSError:
        return {"ok": False, "error": "backend_error", "message": "无法执行 GmSSL 加密。"}

    try:
        with out_file.open("rb") as ciphertext:
            valid_ciphertext = (
                ciphertext.read(1) == b"\x30" and 8 <= out_file.stat().st_size <= 1024
            )
    except OSError:
        valid_ciphertext = False
    if completed.returncode != 0 or not valid_ciphertext:
        return {"ok": False, "error": "encryption_error", "message": "SM2 加密失败。"}
    return {"ok": True, "algorithm": "SM2"}


def sm2_dec(input_file: Path, out_file: Path, *, key_id: str) -> dict[str, Any]:
    """Decrypt a server-resolved SM2 DER file without returning plaintext."""
    key_files = keystore.find_sm2_key(key_id)
    if key_files is None:
        return {"ok": False, "error": "unknown_key", "message": "未配置该密钥标识。"}
    private_key_file, password_file = key_files
    try:
        if private_key_file.is_symlink() or not private_key_file.is_file():
            return {"ok": False, "error": "key_unavailable", "message": "未配置私钥文件。"}
        if password_file.is_symlink():
            return {"ok": False, "error": "invalid_password_file", "message": "口令文件无效。"}
        with password_file.open("rb") as password_stream:
            password_bytes = password_stream.read(1025)
        passphrase = password_bytes.decode("utf-8").removesuffix("\n").removesuffix("\r")
        if not passphrase or len(password_bytes) > 1024 or "\x00" in passphrase:
            return {"ok": False, "error": "invalid_password_file", "message": "口令文件无效。"}
        # This teaching CLI still exposes -pass in the child process argv.
        # Do not log arguments, raw stderr, or exceptions containing the command.
        completed = subprocess.run(
            [
                str(GMSSL_BIN),
                "sm2decrypt",
                "-key",
                str(private_key_file),
                "-pass",
                passphrase,
                "-in",
                str(input_file),
                "-out",
                str(out_file),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "backend_or_key_unavailable",
            "message": "GmSSL 或口令文件不存在。",
        }
    except UnicodeError:
        return {
            "ok": False,
            "error": "invalid_password_file",
            "message": "口令文件需要 UTF-8 编码。",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "message": "GmSSL 解密超时。"}
    except OSError:
        return {"ok": False, "error": "backend_error", "message": "无法执行 GmSSL 解密。"}

    try:
        valid_plaintext = out_file.is_file() and out_file.stat().st_size <= 255
    except OSError:
        valid_plaintext = False
    if completed.returncode != 0 or not valid_plaintext:
        return {"ok": False, "error": "decryption_error", "message": "SM2 解密失败。"}
    return {"ok": True, "algorithm": "SM2"}
