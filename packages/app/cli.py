"""Thin entry adapter. It never chooses tools or implements an Agent Loop."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[2]
LEARNER_MODULE = "packages.app.agent"
Runner = Callable[..., Coroutine[Any, Any, dict[str, object]]]


def status(repo: Path = REPO) -> dict[str, object]:
    """Report file presence only; do not claim that business execution passed."""
    return {
        "entry": "python -m packages.app",
        "entry_ready": True,
        "learner_entry_present": (repo / "packages/app/agent.py").is_file(),
        "learner_entry": "packages.app.agent.run",
        "business_verified": False,
        "network_requests": 0,
        "next_steps": "README.md",
    }


def _load_runner() -> Runner:
    module = importlib.import_module(LEARNER_MODULE)
    runner = getattr(module, "run", None)
    if not callable(runner) or not inspect.iscoroutinefunction(runner):
        raise TypeError("Learner entry must be an async run function")
    return cast(Runner, runner)


def _emit(value: dict[str, object]) -> None:
    print(json.dumps(value, ensure_ascii=False, allow_nan=False))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="密码工具 Agent 的启动入口")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="检查入口与学习者文件状态；不调用模型或密码工具")
    run_parser = commands.add_parser("run", help="调用已迁移的 packages.app.agent.run")
    run_parser.add_argument("--question", required=True, help="输入需求，权限由实际执行器校验")
    args = parser.parse_args(argv)

    if args.command == "status":
        _emit(status())
        return 0

    if not args.question.strip():
        parser.error("question不能为空")

    try:
        runner = _load_runner()
    except ModuleNotFoundError as exc:
        if exc.name in {LEARNER_MODULE, "packages.app.agent"}:
            _emit({"error": "learner_entry_missing", "next_steps": "README.md"})
            return 2
        _emit({"error": "learner_dependency_missing"})
        return 3
    except Exception:
        # Import/validation errors can contain secrets; show a stable code, not the exception text.
        _emit({"error": "learner_entry_load_failed"})
        return 3

    try:
        result: dict[str, object] = asyncio.run(runner(question=args.question))
        if not isinstance(result, dict):
            raise TypeError("Learner entry must return a JSON object")
        _emit(result)
    except KeyboardInterrupt:
        _emit({"error": "interrupted"})
        return 130
    except Exception:
        _emit({"error": "learner_execution_failed"})
        return 3
    # This means the entry returned JSON; task success is determined by the learner's result.
    return 0
