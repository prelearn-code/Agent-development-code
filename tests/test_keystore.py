"""keystore.find_key：通用 key_id → 密钥目录查找。"""

import json
from pathlib import Path

import pytest
from packages.crypto import keystore


def _make_key_dir(root: Path, key_id: str, *, algorithm: str = "SM2") -> Path:
    directory = root / key_id
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        json.dumps({"key_id": key_id, "algorithm": algorithm, "purpose": "sign"}),
        encoding="utf-8",
    )
    return directory


@pytest.mark.parametrize("algorithm", ["SM2", "RSA", "AES"])
def test_find_key_reads_directory_and_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, algorithm: str
) -> None:
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path)
    key_id = algorithm.lower() + "_" + "a" * 32
    directory = _make_key_dir(tmp_path, key_id, algorithm=algorithm)

    bundle = keystore.find_key(key_id)
    assert bundle is not None
    assert bundle.directory == directory
    assert bundle.private_key == directory / "private.pem"
    assert bundle.public_key == directory / "public.pem"
    assert bundle.password_file == directory / "password.txt"
    assert bundle.algorithm == algorithm


def test_find_key_rejects_unknown_and_malformed_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path)
    assert keystore.find_key("not-a-key") is None
    assert keystore.find_key("sm2_short") is None
    assert keystore.find_key("sm2_" + "f" * 32) is None


def test_find_key_rejects_default_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path)
    _make_key_dir(tmp_path, "default")
    assert keystore.find_key("default") is None


def test_find_key_rejects_metadata_mismatch_and_oversize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path)
    key_id = "sm2_" + "b" * 32
    directory = _make_key_dir(tmp_path, key_id)

    (directory / "metadata.json").write_text(
        json.dumps({"key_id": "sm2_" + "c" * 32, "algorithm": "SM2"}),
        encoding="utf-8",
    )
    assert keystore.find_key(key_id) is None

    (directory / "metadata.json").write_text(
        json.dumps({"key_id": key_id, "algorithm": "SM2"}) + " " * 5000,
        encoding="utf-8",
    )
    assert keystore.find_key(key_id) is None


def test_find_key_rejects_symlinked_root_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    link_root = tmp_path / "keys"
    link_root.symlink_to(real_root)
    monkeypatch.setattr(keystore, "_KEY_DIR", link_root)
    assert keystore.find_key("sm2_" + "d" * 32) is None

    monkeypatch.setattr(keystore, "_KEY_DIR", tmp_path)
    key_id = "sm2_" + "e" * 32
    target = _make_key_dir(tmp_path, "target_" + "e" * 32)
    (tmp_path / key_id).symlink_to(target)
    assert keystore.find_key(key_id) is None
