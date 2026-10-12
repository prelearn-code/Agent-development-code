# 密码工具 Agent 开发仓库

按[主学习路径](../Agent-development-doc/00-ROADMAP.md)的**V0环境→V1核心调用→V2基础网页→V3一个MCP→V4审批/恢复→V5知识与可靠性→V6完整实验/交付**推进。目标1–16、P0/M任务ID是技术验收索引，完整标准与步骤在同级文档仓库。

先关注`packages/core`、`packages/crypto`、`tools`、`packages/llm`、`minimal_agent`和薄入口`packages/app`。后续扩展位置已保留，目录存在不代表功能完成。当前已实现：核心类型/配置/日志、CLI入口适配与骨架检查；证书/摘要工具、执行器、LLM客户端和手写Loop仍待你实施。

## 1. 当前能运行的入口

从代码仓库根目录执行：

```bash
python3 scripts/selftest.py --stage V1
python3 -m packages.app status
```

`status`只检查入口与学习者文件是否存在，不调用模型、网络或密码操作，始终不声称业务已验证。它可在安装第三方依赖前运行。当前运行下面命令会明确返回`learner_entry_missing`和退出码2，因为本人手写的runner尚未实现：

```bash
python3 -m packages.app run --question '检查教学证书的有效期'
```

本人创建`minimal_agent/runner.py`并实现`async run(*, question: str) -> dict[str, object]`后，同一个命令会调用它一次并打印JSON；CLI不实现模型循环、选工具、授权或重试。返回0表示入口正常返回JSON，不替代任务成功谓词；业务失败与状态由实际结果解释。详见[从核心开始](docs/CORE-FIRST.md)。

## 2. 后续实际开发与运行在Ubuntu

本次仓库调整在用户指定的D盘本地完成并推送；**WSL仓库由用户自行同步**。之后依赖安装、模型/密码操作、API、前端构建与业务测试按指南在Ubuntu ext4工作目录执行；Windows用浏览器访问页面。D盘结构/入口检查不构成Ubuntu业务验收。

```bash
cd /home/zsw/work/agent_development/Agent-development-code
git status --short --branch
# 工作区干净时，用户自行同步；已有修改先提交或保留并处理冲突
git pull --ff-only
python3 scripts/selftest.py --stage V1
```

环境缺失时按指南P0准备Python3.12与uv；已有venv先检查，不覆盖本地配置：

```bash
uv sync --extra m1 --extra dev
source .venv/bin/activate
# 仅缺少.env时复制样例；不覆盖自己的配置
test -f .env || cp .env.example .env
python -m packages.app status
python -m pytest -q
```

安装项目后亦可用`crypto-agent status`，等价于模块入口。Ollama按Ubuntu回环配置；首次真实请求见文档P0，不将`status`当真实推理。OpenSSL/GmSSL源码与文档/代码同级，源码与安装prefix分开。

## 3. 按阶段补功能

| 阶段 | 核心成果 | 当前或后续位置 |
|---|---|---|
| V0 | 配置、首测与真实模型请求 | core/scripts/tests；请求由本人验证 |
| V1 | 两只读密码工具、唯一执行入口、本人Loop/Trace | crypto/tools/llm/minimal_agent |
| V2 | JSON API、任务持久化、第一网页 | db/services/agent_api/web/infra |
| V3 | 一个Crypto MCP Server，直调对照 | mcp_integration/client/server_crypto |
| V4 | 一种认证加密、固定审批、账本/恢复、状态检查 | crypto/tools/db/graph/verifier |
| V5 | RAG/引用/完整Verifier/Memory/SSE | pipelines/memory/verifier/API/Web |
| V6 | 补工具/MCP/六查询、实验/安全、完整前端/部署 | 现有模块逐项补齐，worker按需 |

`phase0-done`、`m1-done`等专项标签须技术全表通过；V3单Server不等于完整MCP，V2网页不等于目标15毕业。交付与切片预算见[学习计划](../Agent-development-doc/03-LEARNING-ORDER.md)。

## 4. 依赖组保持兼容，按需引入

| 组 | 时机 | 说明 |
|---|---|---|
| m1/dev | V0/V1 | 基础类型、配置、HTTP与开发工具 |
| m2 | V2 | API/SQL/迁移；依赖组名称不是阶段号 |
| mcp | V3 | 单MCP SDK；不提前要求Graph实现 |
| workflow | V4 | Graph/checkpointer |
| m3/ml | V5按需 | 检索/解析/分词；torch等按实际路线验证 |
| m4 | 完整兼容组 | 保留原MCP+Graph组合，可选择细分组 |

本次没有实现密码Provider或生成密钥。`crypto`依赖组由你确定CLI/库/绑定路线并验证后添加，与实际lock同步；不调用不存在的extra。`uv.lock`由实际Ubuntu环境验证，已有用户锁文件自行保留，骨架更新不覆盖它。

## 5. 验证与资料

```bash
python3 scripts/selftest.py --stage V1 --strict
python -m pytest -q
python -m ruff check packages/app tests/test_entry.py scripts/selftest.py
python -m mypy packages/app
```

自检只验证所选阶段目录、配置对齐、普通Python导入分层和文档索引；**不证明Agent、密码业务或安全边界完成**。每次新增业务仍需独立对照、正常/失败/权限与恢复证据。未来`--stage V3/V4/...`按当前阶段检查布局，不自动创建功能或打标签。

- [CORE-FIRST](docs/CORE-FIRST.md)：先写哪些文件、如何接启动入口。
- [STRUCTURE](docs/STRUCTURE.md)：目录职责、分层和扩展时机。
- [AGENTS](AGENTS.md)：AI协作与本人手写边界。
- [同步说明](docs/GIT-SYNC.md)：只在用户指定仓库修改，WSL用户自行拉取。
- [完整步骤](../Agent-development-doc/05-UBUNTU-STEP-BY-STEP.md)：技术标准、81任务与86入口导航。
