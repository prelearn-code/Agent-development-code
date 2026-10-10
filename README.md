# Agent Development Code

> 学习项目实施仓库。目标：**独立实现、解释并验证**一个有证据、可恢复、受权限约束的本地专业领域 Agent 系统。
>
> 学习指南（16 个目标、验收标准、评测数据集）在 `../Agent-development-doc/`。
> 本项目是**指南的产物**，不是指南的一部分。两者独立管理、独立提交。

---

## 快速开始（WSL Ubuntu-22.04）

```bash
# 0. 先验证骨架自洽（纯标准库，不需要装任何依赖）
python3 scripts/selftest.py

# 1. 建虚拟环境。WSL 自带 3.10，项目要 3.12 —— 用 uv 拉，不要 apt 装
uv venv --python 3.12 .venv
source .venv/bin/activate

# 2. 装 M1 依赖（不要一次装全；ml 组含 torch 约 2.5GB，留到 M3 后段）
uv sync --extra m1 --extra dev

# 3. 配置（.env 不进 git）
cp .env.example .env
#    改 OLLAMA_BASE_URL 为 Windows 宿主 IP：
#    ip route show default | awk '{print $3}'

# 4. 验证 Ollama 连通
uv run python -c "
import httpx, os
base = os.environ.get('OLLAMA_BASE_URL', 'http://172.26.0.1:11434')
print(httpx.get(f'{base}/api/version', timeout=5).json())
"

# 5. 跑测试
uv run pytest -q
```

Phase 0 完成判据见指南 `00-ROADMAP.md` §2：**从新终端进入虚拟环境能运行最小请求和一个测试，
配置中没有真实密钥，标记 `phase0-done`。**

---

## 环境拓扑

```
┌─ Windows ─────────────────────────────┐
│ Ollama (GPU) 监听 0.0.0.0:11434        │  ← 保留在宿主：GPU 已生效，模型已下载
└───────────────────────────────────────┘
              ▲ 宿主 IP:11434（NAT 模式下不能用 localhost）
┌─ WSL Ubuntu-22.04 ────────────────────┐
│ ~/projects/Agent-development-code   │  ← 本仓库，放在 ext4，不要放 /mnt/d
│ 原生 Docker 29.1.3 (cgroup v2)         │  ← M1 sandbox、M2 基础设施
│ uv + Python 3.12                       │
└───────────────────────────────────────┘
```

**为什么仓库必须在 WSL 的 ext4 上**：`/mnt/d` 走 9P 协议，
venv / node_modules 这类大量小文件操作会慢数倍。

**为什么 Ollama 留在 Windows**：GPU 直通已生效、三个模型已下载，
迁移需要重拉（其中一个 16.5GB）。WSL 内通过宿主 IP 访问即可。

详见指南 [01-ENVIRONMENT.md](../Agent-development-doc/01-ENVIRONMENT.md)。

---

## 依赖分组（按里程碑引入，不要一次装全）

| 分组 | 引入时机 | 内容 |
|---|---|---|
| `m1` | 现在 | pydantic / httpx / pydantic-settings |
| `m2` | M2 | fastapi / uvicorn / sqlalchemy / asyncpg / alembic |
| `m3` | M3 | qdrant-client / pymupdf / rank-bm25 / jieba |
| `m4` | M4 | mcp / langgraph / langgraph-checkpoint-postgres |
| `ml` | M3 后段 | torch（~2.5GB）/ FlagEmbedding / transformers |
| `dev` | 现在 | pytest / pytest-asyncio / ruff / mypy |

安装示例：`uv sync --extra m1 --extra dev`

---

## 目录

架构与目录归属见 **[docs/STRUCTURE.md](docs/STRUCTURE.md)**（该文件的目录清单由
`scripts/selftest.py` 校验，不会与实现漂移）。

---

## 验证入口

```bash
python3 scripts/selftest.py                    # 骨架自检：布局/配置对齐/密钥/分层
uv run pytest -q                               # 单元与集成测试
uv run ruff check .                            # 静态检查
python3 ../Agent-development-doc/scripts/check_docs.py   # 指南文档检查
```

`scripts/selftest.py` 是**可执行契约**：它检查 `.env.example` 与
`packages/core/config.py` 的字段双向一致，因此不会出现"文档里有、代码里没有"
的配置项。

---

## 阶段产物（每个 tag 应存在的东西）

| Tag | 产物 |
|---|---|
| `phase0-done` | Python 3.12 venv + Ollama 连通 + 一个通过的测试 + 无真实密钥的配置 |
| `m1-tools-done` | `tools/builtin/` 五个工具 + 失败路径测试 + 唯一执行入口拒绝逻辑 |
| `m1-done` | `minimal_agent/` 手写 Loop + `traces/` 原始 NDJSON + 五问说明 |
| `m2-done` | FastAPI + SSE + 9 张表 + 重启不丢 Trace |
| `m3-done` | 入库 + 引用 + 检索消融报告 |
| `m4-done` | 统一执行器 + 审批 + MCP 动态发现 + 恢复 |
| `m5-done` | Memory + 小模型对比 + Verifier + 场景评测 + 安全回归 |
| `m6-done` | Web UI + 干净环境 compose up |

---

## 工作纪律

1. **没有运行证据不勾选完成**。测试通过、Trace 保存、报告有数据。
2. **`minimal_agent/` 和 `verifier/tests/` 必须手写**，AI 只能审查不能代写。
   见指南 [04-AI-ASSISTED-DEV.md](../Agent-development-doc/04-AI-ASSISTED-DEV.md)。
3. **决策记录写进 `docs/decisions/`**，且必须是自己的判断。
4. **不理解就记账**：`docs/to-digest.md` 记录接受但未吃透的代码，每阶段末清空。
5. **draft 与 frozen 分离**：占位符数据不得当作 baseline。

---

## 相关文档

| 文档 | 位置 |
|---|---|
| 主学习路径（16 目标） | `../Agent-development-doc/00-ROADMAP.md` |
| 环境搭建 | `../Agent-development-doc/01-ENVIRONMENT.md` |
| 接口/DDL/SSE/证据契约 | `../Agent-development-doc/repo-structure.md` |
| 模型矩阵与指标口径 | `../Agent-development-doc/02-MODEL-AND-EVAL.md` |
| 学习顺序与节奏 | `../Agent-development-doc/03-LEARNING-ORDER.md` |
| AI 辅助原则 | `../Agent-development-doc/04-AI-ASSISTED-DEV.md` |
| 进度清单 | `../Agent-development-doc/checklist.md` |
| git 同步方式 | [docs/GIT-SYNC.md](docs/GIT-SYNC.md) |
