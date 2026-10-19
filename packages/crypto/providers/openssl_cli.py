"""Fixed OpenSSL executable calls for file digest operations."""

import subprocess
from pathlib import Path
from typing import Any

from packages.core.config import get_settings

_SETTINGS = get_settings()
OPENSSL_BIN = _SETTINGS.openssl_bin
MAX_MESSAGE_BYTES = _SETTINGS.CRYPTO_MAX_FILE_BYTES
TIMEOUT_S = _SETTINGS.CRYPTO_TIMEOUT_S


def sha256_digest_file(input_file: Path) -> dict[str, Any]:
    """Hash a server-resolved file; return only its SHA-256 digest in hex."""
    try:
        completed = subprocess.run(
            [str(OPENSSL_BIN), "dgst", "-sha256", "-binary", str(input_file)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "backend_unavailable", "message": "未找到本地 OpenSSL。"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "message": "OpenSSL 摘要计算超时。"}
    except OSError:
        return {"ok": False, "error": "backend_error", "message": "无法执行 OpenSSL 摘要计算。"}

    if completed.returncode != 0 or len(completed.stdout) != 32:
        return {"ok": False, "error": "digest_error", "message": "SHA-256 摘要计算失败。"}
    return {"ok": True, "algorithm": "SHA-256", "digest_hex": completed.stdout.hex()}
