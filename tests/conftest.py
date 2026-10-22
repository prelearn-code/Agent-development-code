"""测试辅助：可选的调用过程输出。

用法：

    pytest -s -q --flow          # 显示每个用例里 flow(...) 打印的对话/结果
    DSH_LIVE_TEST=1 pytest -s -q tests/test_live_flow.py   # 真实模型 + MCP 的完整输出

没有 --flow 时，print 仍会被 pytest 捕获，只在失败时显示，不会污染正常输出。
"""

from __future__ import annotations

import json
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--flow",
        action="store_true",
        default=False,
        help="显示测试中的模型/工具调用过程（配合 -s 使用）",
    )


def _render(payload: Any) -> str:
    if isinstance(payload, dict | list):
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return str(payload)


@pytest.fixture
def flow(request: pytest.FixtureRequest):
    """把一段过程打印成 `[flow] 标题` + JSON，便于和直接调用 CLI 的输出对照。"""

    def show(title: str, payload: Any = None) -> None:
        if not request.config.getoption("--flow"):
            return
        print(f"\n[flow] {title}")
        if payload is not None:
            print(_render(payload))

    return show
