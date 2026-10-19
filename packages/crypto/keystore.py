"""Existing local SM2 teaching keys and key-id lookup."""

import json
import re
import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from packages.core.config import get_settings

_KEY_DIR = get_settings().crypto_key_root
_KEY_ID_PATTERN = re.compile(r"[a-z][a-z0-9]{1,7}_[0-9a-f]{32}")

# 受信任的外部密钥（教学环境的 "default" 等）；值为 (私钥, 口令) 路径。
CONFIGURED_KEYS: dict[str, tuple[Path, Path]] = {
    "default": (_KEY_DIR / "default" / "private.pem", _KEY_DIR / "default" / "password.txt"),
}


@dataclass(frozen=True)
class KeyBundle:
    """一个密钥目录的完整视图；文件是否存在由调用方判断（不在这里隐式过滤）。"""

    key_id: str
    algorithm: str
    purpose: str
    directory: Path
    private_key: Path  # 私钥；对称密钥时放密钥材料
    public_key: Path  # 仅非对称有意义，可能不存在
    password_file: Path


def generate_sm2_key() -> dict[str, Any]:
    """调用本地 GmSSL 生成测试用 SM2 公私钥对，不接受路径或口令参数。

    私钥及随机保护口令保存在服务端 keys/<key_id> 下。
    返回 key_id 和 public_key_pem，可直接用于签名和验签；不返回私钥或口令。
    每次调用生成新密钥，不应自动重试。本工具不提供生产密钥管理和审批。
    """
    from packages.crypto.providers import gmssl_cli

    key_id = f"sm2_{uuid4().hex}"
    metadata = {
        "key_id": key_id,
        "algorithm": "SM2",
        "purpose": "sign",
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        root = _KEY_DIR
        if root.is_symlink():
            raise OSError("key root is a link")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Never chmod an arbitrary configured directory (for example /tmp).
        # Existing key roots must already be private; new ones use mode 0700.
        if root.stat().st_mode & 0o077:
            raise OSError("key root permissions are too broad")
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=root) as directory:
            pending = Path(directory)
            private_key = pending / "private.pem"
            public_key = pending / "public.pem"
            password_file = pending / "password.txt"
            # 独立的 0700 临时目录和 0600 文件，完成后再发布整个目录。
            for path in (private_key, public_key, password_file):
                path.touch(mode=0o600, exist_ok=False)
            passphrase = secrets.token_urlsafe(32)
            password_file.write_text(passphrase, encoding="utf-8")
            completed = gmssl_cli.generate_keypair(private_key, public_key, passphrase)
            if completed.returncode != 0 or private_key.stat().st_size == 0:
                return {
                    "ok": False,
                    "error": "key_generation_error",
                    "message": "GmSSL 密钥生成失败。",
                }
            with public_key.open("rb") as stream:
                public_bytes = stream.read(4097)
            public_pem = public_bytes.decode("ascii")
            if (
                len(public_bytes) > 4096
                or not public_pem.startswith("-----BEGIN PUBLIC KEY-----\n")
                or not public_pem.rstrip().endswith("-----END PUBLIC KEY-----")
            ):
                return {
                    "ok": False,
                    "error": "key_generation_error",
                    "message": "生成的公钥格式无效。",
                }
            info_file = pending / "metadata.json"
            info_file.touch(mode=0o600, exist_ok=False)
            info_file.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
            pending.rename(root / key_id)
    except FileNotFoundError:
        return {"ok": False, "error": "backend_unavailable", "message": "未找到本地 GmSSL。"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "message": "GmSSL 密钥生成超时。"}
    except (OSError, UnicodeError):
        return {"ok": False, "error": "key_storage_error", "message": "无法生成或保存密钥。"}
    return {"ok": True, **metadata, "public_key_pem": public_pem}


def find_key(key_id: str) -> KeyBundle | None:
    """按 key_id 找到 `keys/<key_id>/`，与算法无关。

    只校验 ID 形状、目录/metadata 完整性；**不检查私钥/口令文件是否存在**，
    否则"目录和 metadata 都对、但私钥丢了"会从 `key_unavailable` 变成
    `unknown_key`，改变错误语义。
    """
    if _KEY_DIR.is_symlink():
        return None
    configured = CONFIGURED_KEYS.get(key_id)
    if configured is not None:
        private_key, password_file = configured
        return KeyBundle(
            key_id=key_id,
            algorithm="SM2",
            purpose="configured",
            directory=private_key.parent,
            private_key=private_key,
            public_key=private_key.with_name("public.pem"),
            password_file=password_file,
        )
    # 仅解析服务端生成的标识；重启后无需依赖内存中的注册表。
    if _KEY_ID_PATTERN.fullmatch(key_id) is None:
        return None
    directory = _KEY_DIR / key_id
    metadata_file = directory / "metadata.json"
    if directory.is_symlink() or metadata_file.is_symlink() or not metadata_file.is_file():
        return None
    try:
        with metadata_file.open("rb") as stream:
            metadata_bytes = stream.read(4097)
        if len(metadata_bytes) > 4096:
            return None
        metadata = json.loads(metadata_bytes)
    except (OSError, UnicodeError, ValueError):
        return None
    algorithm = metadata.get("algorithm") if isinstance(metadata, dict) else None
    if (
        not isinstance(metadata, dict)
        or metadata.get("key_id") != key_id
        or not isinstance(algorithm, str)
        or not algorithm
    ):
        return None
    return KeyBundle(
        key_id=key_id,
        algorithm=algorithm,
        purpose=str(metadata.get("purpose", "")),
        directory=directory,
        private_key=directory / "private.pem",
        public_key=directory / "public.pem",
        password_file=directory / "password.txt",
    )
