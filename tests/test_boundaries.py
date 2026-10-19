"""边界护栏：模型请求与工具执行只能从固定出口发生。"""

import ast
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("packages", "tools", "services", "mcp_integration", "graph", "verifier")
SKIP_PARTS = {"tests", "__pycache__", ".venv", ".git"}
NETWORK_ROOTS = {"urllib", "httpx", "requests", "aiohttp"}
ALLOWED_NETWORK_PREFIX = "packages/llm/"
ALLOWED_CALL_TOOL = "tools/executor.py"


def _sources() -> Iterator[tuple[str, str]]:
    """遍历生产代码，返回 (相对路径, 源码)。测试目录不扫描：测试可以直连 MCP。"""
    for directory in SCAN_DIRS:
        for path in sorted((REPO / directory).rglob("*.py")):
            if SKIP_PARTS & set(path.parts):
                continue
            yield path.relative_to(REPO).as_posix(), path.read_text(encoding="utf-8")


def _call_tool_lines(source: str) -> list[int]:
    """返回源码中 `.call_tool(...)` 调用的行号。"""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "call_tool"
    ]


def _network_imports(source: str) -> set[str]:
    """返回源码导入的网络库根模块名（urllib / httpx / requests / aiohttp）。"""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found & NETWORK_ROOTS


def test_session_call_tool_only_in_executor() -> None:
    offenders = [
        f"{relative}:{line}"
        for relative, source in _sources()
        for line in _call_tool_lines(source)
        if relative != ALLOWED_CALL_TOOL
    ]
    assert offenders == [], f"session.call_tool 只能出现在 {ALLOWED_CALL_TOOL}：{offenders}"


def test_network_imports_stay_in_llm_layer() -> None:
    offenders = [
        relative
        for relative, source in _sources()
        if _network_imports(source) and not relative.startswith(ALLOWED_NETWORK_PREFIX)
    ]
    assert offenders == [], f"网络库导入只允许在 {ALLOWED_NETWORK_PREFIX} 下：{offenders}"


def test_checker_detects_violation() -> None:
    """检查器本身要能抓到违规，否则护栏是空壳。"""
    assert _call_tool_lines("async def f(session):\n    await session.call_tool('x', {})\n") == [2]
    assert _network_imports("import httpx\n") == {"httpx"}
    assert _network_imports("from urllib.request import urlopen\n") == {"urllib"}
    assert _network_imports("import json\n") == set()
