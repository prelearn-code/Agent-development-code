"""执行层授权闸门：未知工具 / 坏参数 / 越权资源 / 未审批写操作，都在调 MCP 之前被拒。"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult
from packages.core.config import Settings
from tools import executor
from tools.registry import build_toolspecs

SHA256_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "sha256_file",
        "description": "摘要",
        "parameters": {
            "type": "object",
            "properties": {"file_id": {"type": "string", "x-resource": "file"}},
            "required": ["file_id"],
        },
    },
}

SIGN_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "sm2_sign_message",
        "description": "签名",
        "parameters": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "x-resource": "file"},
                "key_id": {"type": "string", "x-resource": "key"},
            },
            "required": ["file_id", "key_id"],
        },
    },
}

GENERATE_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "sm2_generate_key",
        "description": "生成密钥",
        "parameters": {"type": "object", "properties": {}},
    },
}


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把数据根目录指到 tmp，并给一个小的策略上限，避免碰仓库 data/。"""
    root = tmp_path / "data"
    root.mkdir()
    settings = Settings.model_construct(
        CRYPTO_DATA_ROOT=str(root), CRYPTO_MAX_FILE_BYTES=100
    )
    monkeypatch.setattr(executor, "get_settings", lambda: settings)
    return root


def _session(payload: dict[str, object] | None = None) -> AsyncMock:
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[], structured_content=payload if payload is not None else {"ok": True}
    )
    return session


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected_before_mcp(sandbox: Path) -> None:
    session = _session()
    outcome = await executor.execute_tool(session, "run_shell", {}, [SHA256_TOOL])
    assert outcome.error_type == "ToolNotFoundError"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_string_file_id_is_validation_error(sandbox: Path) -> None:
    session = _session()
    outcome = await executor.execute_tool(session, "sha256_file", {"file_id": 123}, [SHA256_TOOL])
    assert outcome.error_type == "ToolValidationError"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_path_traversal_is_permission_error(sandbox: Path) -> None:
    session = _session()
    outcome = await executor.execute_tool(
        session, "sha256_file", {"file_id": "../../etc/passwd"}, [SHA256_TOOL]
    )
    assert outcome.error_type == "ToolPermissionError"
    assert outcome.metadata["wire"]["error"] == "permission_denied"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_file_is_permission_error(sandbox: Path) -> None:
    session = _session()
    outcome = await executor.execute_tool(
        session, "sha256_file", {"file_id": "file_404"}, [SHA256_TOOL]
    )
    assert outcome.error_type == "ToolPermissionError"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_oversized_file_is_permission_error(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = sandbox / "file_001"
    directory.mkdir()
    (directory / "data.md").write_text("x" * 10, encoding="utf-8")
    settings = Settings.model_construct(
        CRYPTO_DATA_ROOT=str(sandbox), CRYPTO_MAX_FILE_BYTES=5
    )
    monkeypatch.setattr(executor, "get_settings", lambda: settings)

    session = _session()
    outcome = await executor.execute_tool(
        session, "sha256_file", {"file_id": "file_001"}, [SHA256_TOOL]
    )
    assert outcome.error_type == "ToolPermissionError"
    assert "message too large" in str(outcome.metadata["message"])
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_tool_invisible_is_not_found(sandbox: Path) -> None:
    session = _session()
    outcome = await executor.execute_tool(
        session,
        "sm2_sign_message",
        {"file_id": "file_001", "key_id": "sm2_test"},
        [SHA256_TOOL],
    )
    assert outcome.error_type == "ToolNotFoundError"
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_policy_denies_write_tool(sandbox: Path) -> None:
    tools = [GENERATE_TOOL]
    specs = build_toolspecs(tools)
    session = _session()
    outcome = await executor.execute_tool(
        session, "sm2_generate_key", {}, tools, specs=specs
    )
    assert outcome.error_type == "ToolPermissionError"
    assert "审批" in str(outcome.metadata["message"])
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_only_tool_still_executes(sandbox: Path) -> None:
    directory = sandbox / "file_001"
    directory.mkdir()
    (directory / "data.md").write_text("content", encoding="utf-8")
    session = _session({"ok": True, "algorithm": "SHA-256", "digest_hex": "a" * 64})
    outcome = await executor.execute_tool(
        session, "sha256_file", {"file_id": "file_001"}, [SHA256_TOOL]
    )
    assert outcome.success is True
    session.call_tool.assert_awaited_once_with("sha256_file", arguments={"file_id": "file_001"})
