"""资源解析与授权闸门。

机制层（`resolve_*` / `pick_message_file`）：把服务端资源 ID 解析成受控路径，
不含授权策略。MCP 服务端工具（07 段复查）与应用侧 executor 共用同一套规则，
避免两份实现漂移。

授权层（`resolve_file` / `require_message_file` / `require_key`）：把机制层失败
统一转成 `ToolPermissionError`，只服务应用侧。

身份与项目归属（"这个文件属于谁"）属于 05/06 段，本模块现在只做资源边界。
"""

from __future__ import annotations

import re
from pathlib import Path

from packages.core.config import get_settings
from packages.core.errors import ToolPermissionError
from packages.crypto import keystore

_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")
OUTPUT_FILES = frozenset({"signature.der", "ciphertext.der", "decrypted.bin"})


class ResourceError(ValueError):
    """资源 ID 不可用：格式、越界、不存在、不唯一或过大。"""


# ---------------------------------------------------------------- 机制层
# 服务端与应用侧共用；root 由调用方传入，测试里的 monkeypatch 仍然有效。


def resolve_file_dir(root: Path, file_id: str) -> Path:
    """`file_id` → 目录；任何不合规都抛 `ResourceError`。"""
    if _ID_PATTERN.fullmatch(file_id) is None:
        raise ResourceError("invalid file ID")
    base = root.resolve()
    candidate = base / file_id
    # 先判软链再 resolve：否则会跟到目标路径，丢失"这一级目录本身是链"的事实。
    if candidate.is_symlink():
        raise ResourceError("file directory unavailable")
    path = candidate.resolve()
    if not path.is_relative_to(base):
        raise ResourceError("path escapes root")
    if not path.is_dir():
        raise ResourceError("file directory unavailable")
    return path


def pick_message_file(directory: Path, *, max_bytes: int) -> Path:
    """在已解析的目录里选出唯一原始文件，并检查大小。"""
    try:
        files = [path for path in directory.iterdir() if path.name not in OUTPUT_FILES]
    except OSError as exc:
        raise ResourceError("file directory unreadable") from exc
    if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
        raise ResourceError("exactly one original file required")
    try:
        size = files[0].stat().st_size
    except OSError as exc:
        raise ResourceError("file unavailable") from exc
    if size > max_bytes:
        raise ResourceError("message too large")
    return files[0]


def resolve_message_file(root: Path, file_id: str, *, max_bytes: int) -> Path:
    """`file_id` → 唯一原始文件（含大小检查）。"""
    return pick_message_file(resolve_file_dir(root, file_id), max_bytes=max_bytes)


def resolve_key(key_id: str) -> keystore.KeyBundle | None:
    """`key_id` → 密钥目录视图；keystore 是密钥格式的权威。"""
    return keystore.find_key(key_id)


# ---------------------------------------------------------------- 授权层
# 应用侧闸门：失败统一转成 ToolPermissionError。


def _root(root: Path | None) -> Path:
    return root if root is not None else get_settings().crypto_data_root


def resolve_file(file_id: str, *, root: Path | None = None) -> Path:
    """把服务端 ID 解析为受控目录；任何不合规都抛 ToolPermissionError。"""
    try:
        return resolve_file_dir(_root(root), file_id)
    except ResourceError as exc:
        raise ToolPermissionError(str(exc), file_id=file_id) from exc


def require_message_file(
    file_id: str,
    *,
    max_bytes: int,
    root: Path | None = None,
) -> Path:
    """`file_id` → 唯一原始文件（含大小上限）；失败抛 ToolPermissionError。"""
    try:
        return resolve_message_file(_root(root), file_id, max_bytes=max_bytes)
    except ResourceError as exc:
        raise ToolPermissionError(str(exc), file_id=file_id) from exc


def require_key(key_id: str) -> keystore.KeyBundle:
    """`key_id` → 密钥目录视图；不存在抛 ToolPermissionError。"""
    bundle = resolve_key(key_id)
    if bundle is None:
        raise ToolPermissionError("unknown key_id", key_id=key_id)
    return bundle
