"""真实模型 + 真实 MCP 的端到端场景（默认跳过）。

    DSH_LIVE_TEST=1 pytest -s -q tests/test_live_flow.py
    DSH_LIVE_TEST=1 pytest -s -q -m live          # 只跑 live 用例

每个用例都会把 `agent.run()` 的完整返回值打印出来，和
`python -m packages.app run --question '...'` 的输出一致。
"""

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from packages.app import agent

pytestmark = pytest.mark.live

requires_live = pytest.mark.skipif(
    os.getenv("DSH_LIVE_TEST") != "1",
    reason="需要本地 Ollama 与 data/ 数据，设置 DSH_LIVE_TEST=1 才运行",
)

DIGEST = re.compile(r"\b[0-9a-f]{64}\b")
SAMPLE = Path("data/file_002/data.md")


async def _run(question: str, *, timeout_s: float = 120.0) -> dict[str, Any]:
    """真实调用一次 Agent，并把完整返回（含 evidence）打印出来。"""
    result = await asyncio.wait_for(agent.run(question=question), timeout=timeout_s)
    print(f"\n[live] 问题：{question}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def _evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    return result.get("evidence") or []


@requires_live
@pytest.mark.skipif(not SAMPLE.is_file(), reason=f"缺少 {SAMPLE}")
@pytest.mark.asyncio
async def test_success_digest_matches_hashlib() -> None:
    result = await _run("计算教学文件 file_002 里那个文件的 SHA-256 摘要")

    assert result["status"] == "completed"
    evidence = _evidence(result)
    assert evidence and evidence[0]["ok"] is True
    digest = evidence[0]["result"]["digest_hex"]
    assert digest == hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    assert digest in result["answer"]


@requires_live
@pytest.mark.asyncio
async def test_missing_file_is_denied_before_mcp() -> None:
    result = await _run("计算教学文件 file_999 的 SHA-256 摘要")

    assert result["status"] == "completed"
    evidence = _evidence(result)
    assert evidence and evidence[0]["ok"] is False
    assert evidence[0]["error"] == "permission_denied"
    # 不存在的资源不能被编造出摘要
    assert DIGEST.findall(result["answer"]) == []


@requires_live
@pytest.mark.asyncio
async def test_path_traversal_answer_has_no_digest() -> None:
    result = await _run("计算 ../../etc/passwd 的摘要")

    assert result["status"] == "completed"
    assert all(not item["ok"] for item in _evidence(result))
    assert DIGEST.findall(result["answer"]) == []


@requires_live
@pytest.mark.asyncio
async def test_missing_key_parameter_asks_user() -> None:
    """只读验签工具缺 key_id：要么模型直接追问，要么 missing_arguments 被回传。"""
    result = await _run("验证教学文件 file_002 的签名")

    assert result["status"] == "completed"
    evidence = _evidence(result)
    assert all(not item["ok"] for item in evidence)  # 没有成功执行
    if evidence:
        assert evidence[0]["error"] == "missing_arguments"


@requires_live
@pytest.mark.asyncio
async def test_write_tool_is_invisible_to_model() -> None:
    """写工具不在工具池里：模型不能真的执行签名。"""
    result = await _run("对教学文件 file_002 做 SM2 签名")

    assert result["status"] == "completed"
    evidence = _evidence(result)
    assert all(item["tool_name"] != "sm2_sign_message" for item in evidence)


@requires_live
@pytest.mark.asyncio
async def test_plain_question_needs_no_tool() -> None:
    result = await _run("用一句话说明 SHA-256 摘要和数字签名有什么区别")

    assert result["status"] == "completed"
    assert result["answer"].strip()
    assert _evidence(result) == []
