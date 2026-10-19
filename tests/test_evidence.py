"""编造检测：答案里的 64 位十六进制必须能追到本 run 的 ToolResult。"""

import copy
import re
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult
from packages.app import agent

DIGEST = re.compile(r"\b[0-9a-f]{64}\b")
FAKE_DIGEST = "1" * 64
REAL_DIGEST = "88036eecf53de118265ae2c33ec3881e8d98cf3a29507fea6c9802ae4e1f7f4f"

SHA256_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "sha256_file",
            "parameters": {
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
                "required": ["file_id"],
            },
        },
    }
]


def unbacked_digests(answer: str, evidence: list[dict[str, Any]]) -> set[str]:
    """返回答案里没有被本 run 工具结果背书的摘要；空集表示通过。"""
    attested = {entry["result"].get("digest_hex") for entry in evidence if entry["ok"]}
    return set(DIGEST.findall(answer)) - attested


def _assistant(
    content: str = "",
    calls: list[dict[str, Any]] | None = None,
    provider_ids: list[str | None] | None = None,
) -> dict[str, Any]:
    """provider_ids 模拟模型侧在 tool_calls[i].id 给出的回执号。"""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        tool_calls: list[dict[str, Any]] = []
        for index, call in enumerate(calls):
            entry: dict[str, Any] = {"function": call}
            if provider_ids is not None and provider_ids[index]:
                entry["id"] = provider_ids[index]
            tool_calls.append(entry)
        message["tool_calls"] = tool_calls
    return message


def _sha256_ok() -> CallToolResult:
    return CallToolResult(
        content=[],
        structured_content={
            "ok": True,
            "algorithm": "SHA-256",
            "digest_hex": REAL_DIGEST,
            "file_id": "file_002",
        },
    )


def _responder(responses: list[dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """按调用顺序返回预置回复；每次调用消耗一条。"""
    sent: list[int] = []

    def respond(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        sent.append(1)
        return responses[len(sent) - 1]

    return respond


@pytest.mark.asyncio
async def test_fabricated_digest_without_tool_call_is_detected() -> None:
    """模型没调工具却给了摘要：evidence 为空，检测器必须抓到。"""
    session = AsyncMock()
    evidence: list[dict[str, Any]] = []
    with patch.object(agent, "call_model", return_value=_assistant(f"SHA-256 是 {FAKE_DIGEST}")):
        text = await agent.chat_turn(
            [],
            "计算 file_002 的 SHA-256 摘要",
            session=session,
            tools=SHA256_TOOLS,
            model="fake",
            base_url="fake",
            evidence=evidence,
        )
    session.call_tool.assert_not_awaited()
    assert evidence == []
    assert unbacked_digests(text, evidence) == {FAKE_DIGEST}


@pytest.mark.asyncio
async def test_attested_digest_passes_and_binds_call_id() -> None:
    """工具真跑过：摘要被 evidence 背书；两个号各归各层。"""
    session = AsyncMock()
    session.call_tool.return_value = _sha256_ok()
    responses = [
        _assistant(
            calls=[{"name": "sha256_file", "arguments": '{"file_id": "file_002"}'}],
            provider_ids=["call_y4tue5za"],
        ),
        _assistant(f"摘要：{REAL_DIGEST}"),
    ]
    snapshots: list[list[dict[str, Any]]] = []

    def respond(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        snapshots.append(copy.deepcopy(messages))
        return responses[len(snapshots) - 1]

    evidence: list[dict[str, Any]] = []
    with patch.object(agent, "call_model", side_effect=respond):
        text = await agent.chat_turn(
            [],
            "计算 file_002 的 SHA-256 摘要",
            session=session,
            tools=SHA256_TOOLS,
            model="fake",
            base_url="fake",
            evidence=evidence,
            run_id="run_test_001",
        )

    session.call_tool.assert_awaited_once_with("sha256_file", arguments={"file_id": "file_002"})
    assert unbacked_digests(text, evidence) == set()
    assert len(evidence) == 1
    assert evidence[0]["run_id"] == "run_test_001"
    assert evidence[0]["tool_name"] == "sha256_file"
    assert evidence[0]["ok"] is True
    # 内部账本号由应用生成，与 provider 的回执号必须分开保存。
    assert evidence[0]["call_id"].startswith("call_0")
    assert evidence[0]["provider_call_id"] == "call_y4tue5za"
    assert evidence[0]["call_id"] != evidence[0]["provider_call_id"]
    assert evidence[0]["duration_ms"] >= 0
    assert evidence[0]["result"]["digest_hex"] == REAL_DIGEST
    tool_messages = [message for message in snapshots[-1] if message.get("role") == "tool"]
    # 协议回执回填 provider 的 id，而不是内部账本号。
    assert tool_messages[0]["tool_call_id"] == "call_y4tue5za"


@pytest.mark.asyncio
async def test_tool_call_id_falls_back_when_provider_omits_id() -> None:
    """provider 没给 id（旧模型/部分后端）时，回落到内部 call_id。"""
    session = AsyncMock()
    session.call_tool.return_value = _sha256_ok()
    responses = [
        _assistant(calls=[{"name": "sha256_file", "arguments": {"file_id": "file_002"}}]),
        _assistant(f"摘要：{REAL_DIGEST}"),
    ]
    snapshots: list[list[dict[str, Any]]] = []

    def respond(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        snapshots.append(copy.deepcopy(messages))
        return responses[len(snapshots) - 1]

    evidence: list[dict[str, Any]] = []
    with patch.object(agent, "call_model", side_effect=respond):
        await agent.chat_turn(
            [],
            "计算 file_002 的 SHA-256 摘要",
            session=session,
            tools=SHA256_TOOLS,
            model="fake",
            base_url="fake",
            evidence=evidence,
        )

    assert evidence[0]["provider_call_id"] is None
    tool_messages = [message for message in snapshots[-1] if message.get("role") == "tool"]
    assert tool_messages[0]["tool_call_id"] == evidence[0]["call_id"]


@pytest.mark.asyncio
async def test_digest_outside_this_run_is_flagged() -> None:
    """工具跑过，但答案里混入了另一个摘要：必须只放行被背书的那一个。"""
    session = AsyncMock()
    session.call_tool.return_value = _sha256_ok()
    responses = [
        _assistant(calls=[{"name": "sha256_file", "arguments": {"file_id": "file_002"}}]),
        _assistant(f"摘要：{REAL_DIGEST}；另一个值：{FAKE_DIGEST}"),
    ]
    snapshots: list[list[dict[str, Any]]] = []

    def respond(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        snapshots.append(copy.deepcopy(messages))
        return responses[len(snapshots) - 1]

    evidence: list[dict[str, Any]] = []
    with patch.object(agent, "call_model", side_effect=respond):
        text = await agent.chat_turn(
            [],
            "计算 file_002 的 SHA-256 摘要",
            session=session,
            tools=SHA256_TOOLS,
            model="fake",
            base_url="fake",
            evidence=evidence,
        )
    assert unbacked_digests(text, evidence) == {FAKE_DIGEST}


@pytest.mark.asyncio
async def test_failed_tool_is_recorded_without_digest() -> None:
    """工具失败时 evidence 必须如实记录 ok=False，答案里不应出现摘要。"""
    session = AsyncMock()
    session.call_tool.return_value = CallToolResult(
        content=[],
        structured_content={
            "ok": False,
            "error": "invalid_file",
            "message": "对应 file_id 文件夹须有一个普通原始文件。",
        },
    )
    responses = [
        _assistant(calls=[{"name": "sha256_file", "arguments": {"file_id": "file_999"}}]),
        _assistant("文件 file_999 不存在，无法计算摘要。"),
    ]
    snapshots: list[list[dict[str, Any]]] = []

    def respond(messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        snapshots.append(copy.deepcopy(messages))
        return responses[len(snapshots) - 1]

    evidence: list[dict[str, Any]] = []
    with patch.object(agent, "call_model", side_effect=respond):
        text = await agent.chat_turn(
            [],
            "计算 file_999 的 SHA-256 摘要",
            session=session,
            tools=SHA256_TOOLS,
            model="fake",
            base_url="fake",
            evidence=evidence,
        )
    assert evidence[0]["ok"] is False
    assert evidence[0]["error"] == "invalid_file"
    assert unbacked_digests(text, evidence) == set()


@pytest.mark.asyncio
async def test_run_id_is_generated_per_turn() -> None:
    """调用方不给 run_id 时自动生成；同一进程内两轮不重复。"""
    session = AsyncMock()
    session.call_tool.return_value = _sha256_ok()
    run_ids: list[str] = []

    for _ in range(2):
        responses = [
            _assistant(calls=[{"name": "sha256_file", "arguments": {"file_id": "file_002"}}]),
            _assistant(f"摘要：{REAL_DIGEST}"),
        ]
        evidence: list[dict[str, Any]] = []
        with patch.object(agent, "call_model", side_effect=_responder(responses)):
            await agent.chat_turn(
                [],
                "计算 file_002 的 SHA-256 摘要",
                session=session,
                tools=SHA256_TOOLS,
                model="fake",
                base_url="fake",
                evidence=evidence,
            )
        run_ids.append(evidence[0]["run_id"])

    assert len(set(run_ids)) == 2
    assert all(re.fullmatch(r"[0-9a-f]{32}", run_id) for run_id in run_ids)
