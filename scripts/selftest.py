#!/usr/bin/env python3
"""骨架自检 —— 纯标准库，不导入任何第三方依赖。

作用：在 uv sync 之前就能验证仓库骨架是否自洽，也可以在 CI 与
"干净 clone 后"作为第一道门禁。

它同时是本仓库**目录布局的权威定义**：scripts/layout.json就是阶段目录契约。

用法：
    python scripts/selftest.py
    python scripts/selftest.py --stage V1 --strict   # 把 WARN 也当失败

退出码：0 通过；1 有 FAIL。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- 目录契约
# 每个条目：路径 -> 负责的里程碑。目录职责同时登记在 README.md。
STAGES = tuple(f"V{i}" for i in range(7))
LAYOUT_FILE = REPO / "scripts/layout.json"

# ---------------------------------------------------------------- 分层契约
# key 不允许 import value 里的顶层包。
LAYERING: dict[str, set[str]] = {
    "packages/core": {
        "services",
        "graph",
        "pipelines",
        "tools",
        "mcp",
        "mcp_integration",
        "packages.app",
        "memory",
        "verifier",
        "packages.llm",
        "packages.db",
        "packages.crypto",
        "packages.security",
    },
    "packages/llm": {
        "services",
        "graph",
        "pipelines",
        "tools",
        "mcp",
        "mcp_integration",
        "packages.app",
        "memory",
        "verifier",
        "packages.db",
    },
    "packages/db": {
        "services",
        "graph",
        "pipelines",
        "tools",
        "mcp",
        "mcp_integration",
        "packages.app",
        "memory",
        "verifier",
    },
}

LAYERING["packages/crypto"] = {
    "packages.app",
    "packages.llm",
    "services",
    "graph",
    "pipelines",
    "mcp_integration",
    "memory",
    "verifier",
    "tools",
}

# ---------------------------------------------------------------- 基本清单
REQUIRED_FILES = [
    "pyproject.toml",
    ".env.example",
    ".gitignore",
    "README.md",
    "AGENTS.md",
    "scripts/layout.json",
    "packages/app/cli.py",
    "packages/app/__main__.py",
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
def check_layout(stage: str = "V1") -> None:
    try:
        manifest = json.loads(LAYOUT_FILE.read_text(encoding="utf-8"))
        if manifest["schema_version"] != 1 or manifest["stages"] != list(STAGES):
            raise ValueError("layout schema/stages mismatch")
        if manifest["default_stage"] != "V1":
            raise ValueError("default stage mismatch")
        entries = manifest["directories"]
        seen: set[str] = set()
        expected: list[str] = []
        structure = (REPO / "README.md").read_text(encoding="utf-8")
        for entry in entries:
            path, introduced = entry["path"], entry["stage"]
            resolved = (REPO / path).resolve()
            if not resolved.is_relative_to(REPO.resolve()) or path.casefold() in seen:
                raise ValueError("unsafe or duplicate layout path")
            seen.add(path.casefold())
            if introduced not in STAGES or f"`{path}/`" not in structure:
                raise ValueError("unknown stage or directory missing from README")
            if STAGES.index(introduced) <= STAGES.index(stage):
                expected.append(path)
        if not expected:
            raise ValueError("empty stage layout")
    except (OSError, ValueError, KeyError, TypeError):
        fail("目录契约", "无法解析layout或与README不一致")
        return

    missing = [path for path in expected if not (REPO / path).is_dir()]
    if missing:
        fail("目录布局", f"{stage}缺少目录: {', '.join(missing)}")
    else:
        ok("目录布局", f"{stage}的{len(expected)}个当前目录齐全；后续功能未据此验收")
    if (REPO / "mcp").exists():
        fail("SDK命名", "项目MCP目录应为mcp_integration，避免遮蔽SDK")
    else:
        ok("SDK命名", "项目包mcp_integration与SDK mcp分开")
    absent = [name for name in REQUIRED_FILES if not (REPO / name).is_file()]
    if absent:
        fail("必备文件", f"缺少: {', '.join(absent)}")
    else:
        ok("必备文件", f"{len(REQUIRED_FILES)}个文件齐全")


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
        if any(
            part in {".git", ".venv", ".check-deps", "__pycache__", "data", "tmp"}
            for part in path.parts
        ):
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


def _imported_modules(node: ast.AST, path: Path) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    module = node.module or ""
    if node.level:
        package = (_module_name(path) or "").split(".")
        if path.name != "__init__.py":
            package = package[:-1]
        keep = len(package) - node.level + 1
        module = ".".join(package[: max(keep, 0)] + ([module] if module else []))
    return [module] + [f"{module}.{alias.name}" for alias in node.names if alias.name != "*"]


def check_layering() -> None:
    """Check regular absolute and relative imports; dynamic loading needs review."""
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
                for module in _imported_modules(node, py):
                    if any(module == b or module.startswith(b + ".") for b in banned):
                        violations.append(f"{py.relative_to(REPO)} -> {module}")
    if violations:
        fail("分层护栏", f"{len(violations)}处反向依赖: {violations[0]}")
    else:
        ok("分层护栏", "core/llm/db/crypto无普通反向import")


def check_tool_spec_guard() -> None:
    """模型层必须包含非幂等工具不得自动重试的守卫。"""
    path = REPO / "packages/core/models.py"
    if not path.is_file():
        fail("工具契约", "models.py 不存在")
        return
    text = path.read_text(encoding="utf-8")
    needed = [
        "read_only",
        "retry",
        "risk_level",
        "input_schema",
        "output_schema",
        "timeout_s",
        "permission",
    ]
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
    for key in ("name =", "version =", "requires-python ="):
        if key not in text:
            fail("pyproject", f"缺少 {key.strip()}")
            return
    if ">=3.12" not in text:
        fail("pyproject", "requires-python 不是 >=3.12")
        return
    ok("pyproject", "name/version/requires-python(>=3.12) 齐备")


def check_ollama_endpoint() -> None:
    """Ollama 与本应用同机，地址必须是回环。

    这个检查的**方向被反转过一次**：旧方案把 Ollama 留在 Windows 宿主，
    Ubuntu 侧必须用宿主 IP，所以当时检查的是"不得写 localhost"。
    现在 Ollama 是 Ubuntu 内的 systemd 服务，跨网络访问的前提已不存在，
    写宿主 IP 或 0.0.0.0 才是错的（见 README 的运行配置）。
    """
    env = REPO / ".env.example"
    if not env.is_file():
        fail("Ollama 地址", ".env.example 不存在")
        return
    match = re.search(r"^OLLAMA_BASE_URL=(\S+)\s*$", env.read_text(encoding="utf-8"), re.M)
    if not match:
        fail("Ollama 地址", ".env.example 缺少 OLLAMA_BASE_URL")
        return
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", match.group(1))
    host = host.split("/")[0].rsplit(":", 1)[0].strip("[]")
    if host in ("127.0.0.1", "localhost", "::1"):
        ok("Ollama 地址", f"回环地址 {host}，与同机 systemd 服务一致")
    else:
        fail(
            "Ollama 地址",
            f"OLLAMA_BASE_URL 指向 {host}；Ollama 与本应用同机，应改为 127.0.0.1",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="骨架自检（纯标准库）")
    ap.add_argument("--strict", action="store_true", help="把 WARN 也视为失败")
    ap.add_argument("--stage", choices=STAGES, default="V1", help="当前交付阶段目录")
    args = ap.parse_args()
    results.clear()

    check_layout(args.stage)
    check_pyproject()
    check_config_parity()
    check_secrets()
    check_gitignore()
    check_layering()
    check_tool_spec_guard()
    check_ollama_endpoint()

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
