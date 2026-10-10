"""local-professional-agent —— 顶层包。

分层规则（见 docs/STRUCTURE.md）：
    packages.core   -> 无 IO，纯逻辑
    packages.llm    -> 只依赖 core
    packages.db     -> 只依赖 core
    tools/          -> 依赖 core
    pipelines/      -> 依赖 core + db
    graph/          -> 依赖以上全部
    services/       -> 依赖以上全部

反向依赖由 scripts/check_layering.py 在 CI 中拦截。
"""

__version__ = "0.0.1"
