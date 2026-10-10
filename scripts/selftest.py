#!/usr/bin/env python3
"""骨架自检 —— 纯标准库，不导入任何第三方依赖。

作用：在 uv sync 之前就能验证仓库骨架是否自洽，也可以在 CI 与
"干净 clone 后"作为第一道门禁。

它同时是本仓库**目录布局的权威定义**：EXPECTED_DIRS 就是架构契约。

用法：
    python scripts/selftest.py
    python scripts/selftest.py --strict 检查   # 把 WARN 也当失败

退出码：0 通过；1 有 FAIL。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- 目录契约
# 每个条目：路径 -> 负责的里程碑。这就是 docs/STRUCTURE.md 的可执行版本。
EXPECTED_DIRS: dict[str, str] = {
    "packages/core": "Phase0/M1 纯逻辑层",
    "packages/llm": "M1 Ollama 客户端",
    "packages/db": "M2 数据库",
    "packages/db/repository": "M2 CRUD",
    "packages/db/queries": "M2 六个验收查询",
    "packages/security": "M1 起策略/RBAC/sandbox/审计",
    "tools/builtin": "M1 五个工具",
    "tools/tests": "M1 工具测试",
    "minimal_agent": "M1 手写 Loop（红线：必须自己写）",
    "minimal_agent/traces": "M1 原始 NDJSON 报文证据",
    "pipelines/ingest": "M3 入库",
    "pipelines/retrieval": "M3 检索与消融",
    "pipelines/citation": "M3 引用构造",
    "mcp/server_fs": "M4 File MCP",
    "mcp/server_db": "M4 Database MCP",
    "mcp/server_domain": "M4 Domain MCP",
    "mcp/client": "M4 动态发现",
    "graph/nodes": "M4 LangGraph 节点",
    "memory": "M5 长期记忆",
    "verifier/checks": "M4 最小检查 / M5 完整验证",
    "verifier/tests": "M5 对抗性测试（红线：必须自己写）",
    "eval/datasets": "M3 起数据集",
    "services/agent-api/routers": "M2 FastAPI",
    "services/agent-worker": "M2 长任务",
    "tests": "端到端集成测试",
    "docs/decisions": "每阶段决策记录",
    "infra": "M2 基础设施",
    "scripts": "校验脚本",
}

# ---------------------------------------------------------------- 分层契约
# key 不允许 import value 里的顶层包。
LAYERING: dict[str, set[str]] = {
    "packages/core": {"services", "graph", "pipelines", "tools", "mcp",
                      "memory", "verifier", "packages.llm", "packages.db"},
    "packages/llm": {"services", "graph", "pipelines", "tools", "mcp",
                     "memory", "verifier", "packages.db"},
    "packages/db": {"services", "graph", "pipelines", "tools", "mcp",
                    "memory", "verifier"},
}

# ---------------------------------------------------------------- 基本清单
REQUIRED_FILES = [
    "pyproject.toml",
    ".env.example",
    ".gitignore",
    "README.md",
    "AGENTS.md",
    "docs/STRUCTURE.md",
    "scripts/selftest.py",
    "packages/core/models.py",
    "packages/core/config.py",
    "packages/core/errors.py",
    "packages/core/logging.py",
]

# .gitignore 必须覆盖的项（漏了就会把密钥或产物提交上去）
GITIGNORE_MUST = [".env", ".venv", "__pycache__", "data/", "eval/results/"]

SECRET_HINTS = re.compile(
    r"(?i)(password|secret|token|api[_-]?key)\s*[=:]\s*"
    r"(?!\s*$)(?!\*{3})(?!CHANGE_ME)(?!required)(?!none\b)"
    r"([^\s#]{6,})"
)

# Python 内置/标准库之外的顶层包，用于 import 检查
STDLIB = set(getattr(sys, "stdlib_module_names", set()))

results: list[tuple[str, str, str]] = []  # (level, check, detail)


def ok(check: str, detail: str = "") -> None:
    results.append(("OK", check, detail))


def fail(check: str, detail: str) -> None:
    results.append(("FAIL", check, detail))


def warn(check: str, detail: str) -> None:
    results.append(("WARN", check, detail))


# ---------------------------------------------------------------- 检查项
def check_layout() -> None:
    missing = [d for d in EXPECTED_DIRS if not (REPO / d).is_dir()]
    if missing:
        fail("目录布局", f"缺少 {len(missing)} 个目录: {', '.join(missing[:6])}")
    else:
        ok("目录布局", f"{len(EXPECTED_DIRS)} 个契约目录齐全")

    absent = [f for f in REQUIRED_FILES if not (REPO / f).is_file()]
    if absent:
        fail("必备文件", f"缺少: {', '.join(absent)}")
    else:
        ok("必备文件", f"{len(REQUIRED_FILES)} 个文件齐全")


def _settings_fields() -> set[str]:
    """从 packages/core/config.py 用 AST 取 Settings 的字段名（不导入模块）。"""
    path = REPO / "packages/core/config.py"
    if not path.is_file():
        return set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    name = stmt.target.id
                    if name.isupper():
                        fields.add(name)
    return fields


def _env_keys() -> set[str]:
    path = REPO / ".env.example"
    if not path.is_file():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def check_config_parity() -> None:
    """配置双向对齐：.env.example <-> Settings。"""
    env, cfg = _env_keys(), _settings_fields()
    if not env or not cfg:
        fail("配置对齐", "无法解析 .env.example 或 config.py 的 Settings")
        return

    only_env = sorted(env - cfg)
    only_cfg = sorted(cfg - env)
    if only_env:
        fail("配置对齐", f".env.example 有但 Settings 没有: {', '.join(only_env)}")
    if only_cfg:
        fail("配置对齐", f"Settings 有但 .env.example 没有: {', '.join(only_cfg)}")
    if not only_env and not only_cfg:
        ok("配置对齐", f"{len(env)} 个键双向一致")


def check_secrets() -> None:
    hits: list[str] = []
    for path in REPO.rglob("*"):
        if not path.is_file() or path.name == "selftest.py":
            continue
        if any(part in {".git", ".venv", "__pycache__", "data"} for part in path.parts):
            continue
        if path.suffix not in {".py", ".toml", ".json", ".yaml", ".yml", ".env", ".example", ".md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in SECRET_HINTS.finditer(text):
            hits.append(f"{path.relative_to(REPO)}: {m.group(1)}")
    if hits:
        fail("密钥泄漏", f"疑似真实密钥 {len(hits)} 处: {hits[0]}")
    else:
        ok("密钥泄漏", "未发现疑似真实密钥")


def check_gitignore() -> None:
    path = REPO / ".gitignore"
    if not path.is_file():
        fail("gitignore", "文件不存在")
        return
    text = path.read_text(encoding="utf-8")
    missing = [p for p in GITIGNORE_MUST if p not in text]
    if missing:
        fail("gitignore", f"缺少: {', '.join(missing)}")
    else:
        ok("gitignore", f"{len(GITIGNORE_MUST)} 项必需排除齐全")


def _module_name(path: Path) -> str | None:
    rel = path.relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else None


def check_layering() -> None:
    """分层护栏：core 不得 import 上层模块。"""
    violations: list[str] = []
    for owner, banned in LAYERING.items():
        owner_dir = REPO / owner
        if not owner_dir.is_dir():
            continue
        for py in owner_dir.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                fail("语法", f"{py.relative_to(REPO)}: {exc}")
                continue
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for mod in mods:
                    root = mod.split(".")[0]
                    full = mod
                    if root in banned or full in banned:
                        violations.append(f"{py.relative_to(REPO)} -> {mod}")
    if violations:
        fail("分层护栏", f"{len(violations)} 处反向依赖: {violations[0]}")
    else:
        ok("分层护栏", "core/llm/db 无反向依赖")


def check_tool_spec_guard() -> None:
    """模型层必须包含非幂等工具不得自动重试的守卫。"""
    path = REPO / "packages/core/models.py"
    if not path.is_file():
        fail("工具契约", "models.py 不存在")
        return
    text = path.read_text(encoding="utf-8")
    needed = ["read_only", "retry", "risk_level", "input_schema",
              "output_schema", "timeout_s", "permission"]
    missing = [n for n in needed if n not in text]
    if missing:
        fail("工具契约", f"ToolSpec 缺少字段: {', '.join(missing)}")
        return
    if "非幂等操作不得自动重试" not in text:
        fail("工具契约", "缺少非幂等工具 retry 守卫")
        return
    ok("工具契约", "ToolSpec 九字段与非幂等守卫齐全")


def check_pyproject() -> None:
    path = REPO / "pyproject.toml"
    if not path.is_file():
        fail("pyproject", "不存在")
        return
    text = path.read_text(encoding="utf-8")
    for key in ('name =', 'version =', 'requires-python ='):
        if key not in text:
            fail("pyproject", f"缺少 {key.strip()}")
            return
    if ">=3.12" not in text:
        fail("pyproject", "requires-python 不是 >=3.12")
        return
    ok("pyproject", "name/version/requires-python(>=3.12) 齐备")


def check_env_placeholder_anthropic() -> None:
    """Ollama 地址不应写成 localhost —— WSL 默认 NAT 下不可达。"""
    env = REPO / ".env.example"
    if env.is_file() and "OLLAMA_BASE_URL=http://localhost" in env.read_text(encoding="utf-8"):
        warn("Ollama 地址", "OLLAMA_BASE_URL 指向 localhost；WSL NAT 模式下不可达，应使用宿主 IP")
    else:
        ok("Ollama 地址", "未误用 localhost")


def main() -> int:
    ap = argparse.ArgumentParser(description="骨架自检（纯标准库）")
    ap.add_argument("--strict", action="store_true", help="把 WARN 也视为失败")
    args = ap.parse_args()

    check_layout()
    check_pyproject()
    check_config_parity()
    check_secrets()
    check_gitignore()
    check_layering()
    check_tool_spec_guard()
    check_env_placeholder_anthropic()

    for level, check, detail in results:
        line = f"[{level}] {check}"
        if detail:
            line += f": {detail}"
        print(line, file=sys.stdout if level == "OK" else sys.stderr)

    fails = sum(1 for lvl, _, _ in results if lvl == "FAIL")
    warns = sum(1 for lvl, _, _ in results if lvl == "WARN")
    print(f"\nSUMMARY checks={len(results)} fails={fails} warns={warns}")

    if fails or (args.strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
