# 架构索引（本文件的目录清单由 scripts/selftest.py 校验）

> 权威接口契约在指南包的 [repo-structure.md](../local-agent-learning-path/repo-structure.md)。
> 本文件只说明"哪个目录归哪个里程碑"，不重新定义接口。

## 分层与依赖方向

```
services/            services/agent-api, services/agent-worker
    |                依赖全部下层
graph/               依赖下面全部
    |
pipelines/  tools/  mcp/  memory/  verifier/
    |                依赖 core + db
packages/db/         只依赖 core
packages/llm/        只依赖 core
    |
packages/core/       无 IO；不 import 任何上层
```

**硬约束**：`packages/core`、`packages/llm`、`packages/db` 不得 import
`services` / `graph` / `pipelines` / `tools` / `mcp` / `memory` / `verifier`。
由 `scripts/selftest.py` 的"分层护栏"检查与 CI 拦截。

## 目录归属

| 目录 | 里程碑 | 内容 | 红线 |
|---|---|---|---|
| `packages/core/` | Phase0–M1 | `ToolResult`/`ToolSpec`/`RiskLevel`/`Policy`、配置、异常、日志 | 无 IO |
| `packages/llm/` | M1 | Ollama 原生 `/api/chat` 客户端、NDJSON 解析、结构化输出、模型路由 | 与前端 SSE 分开适配 |
| `packages/db/` | M2 | async engine、ORM、`repository/`、`queries/q1~q6.sql` | 路由里不写 SQL |
| `packages/security/` | **M1 起** | 策略表、RBAC、sandbox、入参白名单、注入缓解、审计 | 唯一执行入口 |
| `tools/builtin/` | M1 | calculator、read_file、query_database(fixture)、run_python、run_experiment | 走 `execute_tool` |
| `tools/tests/` | M1 | 参数错误/未知工具/越界/空结果/超时清理/输出超限 | 空结果 `success=True` |
| `minimal_agent/` | M1 | **手写** Agent Loop、`traces/` 存原始 NDJSON | **禁止 AI 代写** |
| `pipelines/` | M3 | ingest / retrieval / citation | 每 chunk 存定位元数据 |
| `mcp/` | M4 | 三个 server + client 动态发现 | 日志走 stderr |
| `graph/` | M4 | State、节点、条件边、checkpoint、interrupt | State 不塞大对象 |
| `memory/` | M5 | Extractor、Importance Filter、去重、检索 | 不是每条消息都进 memory |
| `verifier/` | M4 最小 / M5 完整 | 检查项与对抗性测试 | **对抗测试禁止 AI 代写** |
| `eval/` | M3 起 | 数据集、runner、metrics、compare | draft/frozen 分离 |
| `services/` | M2 | FastAPI 路由、middleware、SSE | `run_id` 在生成器前生成 |
| `tests/` | 全程 | 端到端：恢复、持久化、注入 | 需要真实运行证据 |
| `docs/decisions/` | 每阶段 | 决策记录 | **禁止 AI 代写** |
| `infra/` | M2 | compose、Dockerfile、init SQL | 开发端口绑 127.0.0.1 |

## 环境拓扑（决策：见指南 01-ENVIRONMENT.md §2）

```
Windows  ─ Ollama (GPU, 0.0.0.0:11434)  ← 保留在宿主
   ▲ 宿主机 IP:11434
WSL Ubuntu-22.04
   ├─ ~/projects/local-professional-agent   ← 本仓库（ext4）
   ├─ 原生 Docker 29.1.3                    ← M1 sandbox / M2 基础设施
   └─ uv + Python 3.12
```

## 验证入口

```bash
python scripts/selftest.py            # 纯标准库，uv sync 之前即可运行
uv sync --extra m1 --extra dev        # M1 依赖
uv run pytest -q
```
