"""资源解析机制层与应用侧闸门的单元测试。"""

from pathlib import Path

import pytest
from packages.core.config import Settings
from packages.core.errors import ToolPermissionError
from packages.security import resources


def _data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root


def test_resolve_file_dir_accepts_valid_id(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    (root / "file_002").mkdir()
    assert resources.resolve_file_dir(root, "file_002") == (root / "file_002").resolve()


@pytest.mark.parametrize("file_id", ["../etc", "file/001", "", "a" * 129, "file 001"])
def test_resolve_file_dir_rejects_bad_format(tmp_path: Path, file_id: str) -> None:
    root = _data_root(tmp_path)
    with pytest.raises(resources.ResourceError):
        resources.resolve_file_dir(root, file_id)


def test_resolve_file_dir_rejects_missing_and_symlink(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    with pytest.raises(resources.ResourceError):
        resources.resolve_file_dir(root, "file_404")
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "file_003").symlink_to(outside)
    with pytest.raises(resources.ResourceError):
        resources.resolve_file_dir(root, "file_003")


def test_pick_message_file_excludes_outputs_and_checks_size(tmp_path: Path) -> None:
    directory = _data_root(tmp_path) / "file_004"
    directory.mkdir()
    (directory / "data.md").write_text("x" * 10, encoding="utf-8")
    (directory / "signature.der").write_bytes(b"artifact")
    picked = resources.pick_message_file(directory, max_bytes=100)
    assert picked.name == "data.md"
    with pytest.raises(resources.ResourceError):
        resources.pick_message_file(directory, max_bytes=5)


def test_pick_message_file_requires_exactly_one_file(tmp_path: Path) -> None:
    directory = _data_root(tmp_path) / "file_005"
    directory.mkdir()
    with pytest.raises(resources.ResourceError):
        resources.pick_message_file(directory, max_bytes=100)
    (directory / "a.bin").write_bytes(b"a")
    (directory / "b.bin").write_bytes(b"b")
    with pytest.raises(resources.ResourceError):
        resources.pick_message_file(directory, max_bytes=100)


def test_resolve_key_returns_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.crypto import keystore

    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path / "keys")
    key_id = "sm2_" + "d" * 32
    directory = tmp_path / "keys" / key_id
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        '{"key_id": "' + key_id + '", "algorithm": "SM2", "purpose": "sign"}',
        encoding="utf-8",
    )
    bundle = resources.resolve_key(key_id)
    assert bundle is not None
    assert bundle.directory == directory
    assert bundle.private_key == directory / "private.pem"
    assert bundle.public_key == directory / "public.pem"
    assert bundle.password_file == directory / "password.txt"
    assert resources.resolve_key("not-configured") is None


def test_gates_convert_errors_to_permission_error(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    with pytest.raises(ToolPermissionError) as excinfo:
        resources.resolve_file("../etc", root=root)
    assert excinfo.value.context["file_id"] == "../etc"
    with pytest.raises(ToolPermissionError):
        resources.require_message_file("file_404", max_bytes=10, root=root)
    with pytest.raises(ToolPermissionError) as key_error:
        resources.require_key("not-configured")
    assert key_error.value.context["key_id"] == "not-configured"


def test_gates_return_resolved_paths(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    directory = root / "file_006"
    directory.mkdir()
    (directory / "data.md").write_text("content", encoding="utf-8")
    assert resources.resolve_file("file_006", root=root) == directory.resolve()
    picked = resources.require_message_file("file_006", max_bytes=100, root=root)
    assert picked.name == "data.md"


def test_pick_message_file_rejects_symlinked_message(tmp_path: Path) -> None:
    directory = _data_root(tmp_path) / "file_007"
    directory.mkdir()
    target = tmp_path / "outside.bin"
    target.write_text("x", encoding="utf-8")
    (directory / "data.md").symlink_to(target)
    with pytest.raises(resources.ResourceError):
        resources.pick_message_file(directory, max_bytes=100)


def test_resolve_file_uses_configured_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "data"
    (root / "file_009").mkdir(parents=True)
    settings = Settings.model_construct(CRYPTO_DATA_ROOT=str(root))
    monkeypatch.setattr("packages.security.resources.get_settings", lambda: settings)
    assert resources.resolve_file("file_009") == (root / "file_009").resolve()
