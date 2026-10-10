# AGENTS.md —— 本仓库的 AI 智能体协作规则

> 适用于任何 AI 编码助手（含本 DSH 会话）。
> 完整依据见 `../Agent-development-doc/04-AI-ASSISTED-DEV.md`。
> **这是学习项目，验收标准是"人的能力"，不只是"可运行的产物"。**

---

## 0. 最高优先级：三条红线

以下内容**禁止代写**，只允许审查。若被要求代写，必须先拒绝并说明理由。

| 红线 | 位置 | 为什么 |
|---|---|---|
| **手写 Agent Loop** | `minimal_agent/` | 流式 NDJSON 的 tool_calls 累积、`role:tool` 报文、停止条件、失败回传是 M4 调 LangGraph 的唯一资本。这是整个学习路径的核心资产 |
| **Verifier 检查逻辑与对抗性测试** | `verifier/`、`verifier/tests/` | 要求是"能发现 Tool 返回 12.34 而回答 13.24"。AI 写的检查只覆盖 AI 自己会犯的错，等于让出题人答题 |
| **决策记录** | `docs/decisions/` | 记录的是人的判断。AI 能写出漂亮理由，但那是 AI 的观点，会让"独立思考留痕"失效 |

此外，**禁止**：修改或放宽已有的测试断言；放宽评测的 `success_criteria`；
代写安全注入测试用例；擅自扩大范围重构能通过验收的代码。

---

## 1. 允许与禁止

### 可以放手（AI 写 + 人 review）
- `infra/`（compose、Dockerfile）、CI 配置、`.gitignore`
- 样板代码：Pydantic 模型、router 拆分、middleware、CRUD、日志封装
- SQL DDL 的可执行版本、Alembic 配置
- `web/`（前端不是本项目的能力目标）
- 文档格式整理、索引生成

### 协商（人定接口与验收，AI 填实现）
- `packages/core/models.py` 的契约（改动需同步指南 `repo-structure.md`）
- `packages/security/` 的策略落地（分级判断由人做）
- `pipelines/retrieval/` 的消融开关（实验设计由人做）
- State 字段设计、`interrupt()` 的节点拆分

### 只能审查
- 红线三项
- `tools/builtin/` 里的安全判断（路径白名单、参数校验的**边界**）
- `graph/` 的状态机设计

---

## 2. 每次接受 AI 代码的固定动作

```
[ ] git diff 检查测试文件有没有被改 —— 被改则逐行 review 为什么
[ ] 真正跑测试，不是相信"应该能过"
[ ] 跑 python3 scripts/selftest.py
[ ] 改动涉及 Prompt/检索/工具/流程时，跑评测对比（指南 02-MODEL-AND-EVAL.md §9）
[ ] 至少问一个审查问题（见 §3）
```

**判定 AI 改动是否接受**：

| 评测结果 | 决定 |
|---|---|
| Task Success 上升，其余不降 | 接受 |
| Task Success 持平，延迟明显下降 | 接受 |
| Task Success 下降 > 2pt | **拒绝**，要求解释哪类用例退化 |
| Unauthorized Action Rate > 0 | **拒绝并回滚**，安全不妥协 |
| Unsupported Claim Rate 上升 | 拒绝 |

---

## 3. 推荐的提问方式

**审查代码（最高价值用法）**：
```
这是我写的 <模块>（附代码）。只做以下事，不要重写：
1. 列出所有"假设输入合法"的地方，说明非法输入会发生什么
2. 找出所有可能静默失败（不报错但结果错）的路径
3. 指出 except 捕获过宽的位置
4. 每项给一个能触发它的具体输入
输出表格。不要夸奖，不要总结，不要给改进建议。
```

**对照验收标准**：
```
这是实现，这是验收要求（附上）。逐条判断"完全满足 / 表面满足但边界会破 / 不满足"。
只输出判断表，不要给修改后的代码。
```

**检验理解（用于消化 docs/to-digest.md）**：
```
这段代码我标记为"未吃透"。扮演面试官，一次问一个问题检验我是否真懂，
根据我的回答调整难度。不要提前告诉我答案。
```

**禁止的提问方式**：
```
✗ "你是资深 Agent 架构师，请设计我的 LangGraph State"
   → 把判断权也外包了。正确做法：自己出方案，让 AI 当审查者。
```

---

## 4. 技术约定

### 分层（由 `scripts/selftest.py` 强制）
```
packages/core  ← 无 IO；不 import services/graph/pipelines/tools/mcp/memory/verifier
packages/llm   ← 只依赖 core
packages/db    ← 只依赖 core
pipelines/, tools/, mcp/, memory/, verifier/  ← 依赖 core (+ db)
graph/         ← 依赖以上全部
services/      ← 依赖以上全部
```
**不允许反向依赖。**

### 契约
- `ToolResult` 是 Pydantic 泛型，序列化用 `model_dump_json()`，**不用 dataclass**
- 容器字段一律 `Field(default_factory=...)`
- **空结果是 `success=True`**，不是失败
- 工具 handler 不抛异常；异常由 `execute_tool` 转为 `ToolResult`
- **所有工具调用必须走唯一执行入口 `execute_tool`**，不得直接调 `spec.handler`
- `read_only=False` 的工具 `retry` 必须为 0（`ToolSpec` 有守卫）

### 配置
- 改配置必须**同时**改 `.env.example` 与 `packages/core/config.py`，否则 `selftest.py` 失败
- `.env` 不进 git；`.env.example` 不含真实密钥
- 密钥在日志中必须经 `packages/core/logging.py` 的 `scrub()` 脱敏

### 外部协议
- Ollama 原生 `/api/chat` 是 **NDJSON**；给前端的 `/chat` 是 **SSE**。**两层分开适配，不共用解析器**
- 原生工具消息用 `role:tool` + `tool_name`；`call_id` 由应用生成，不依赖模型给的 id
- **不要预设 arguments 是字符串 delta** —— 以锁定版本的实际 Trace 为准
- MCP server 的**日志必须走 stderr**，stdout 是 JSON-RPC 协议通道

### 环境
- 仓库在 WSL ext4 上；**不要**把它移到 `/mnt/d`
- Ollama 在 Windows 宿主，WSL 内用宿主 IP 而非 `localhost`
- Docker 是 WSL 内原生 29.1.3，**没有** Docker Desktop

---

## 5. 命令

```bash
python3 scripts/selftest.py     # 骨架自检（纯标准库）
uv run pytest -q                # 测试
uv run ruff check .             # 静态检查
uv run mypy packages/           # 类型检查
```

提交前必须 `selftest.py` 与 `pytest` 均通过。

---

## 6. 不理解就记账

接受但未完全消化的代码，记入 `docs/to-digest.md`：

```markdown
| 文件 | 加入日期 | 为什么没吃透 | 计划消化时间 |
|---|---|---|---|
| pipelines/retrieval/fusion.py | 2026-10-20 | RRF 的 k 值含义没搞清 | M3 结束前 |
```

**每阶段结束必须清空。** 清单为空说明在自欺；只增不减说明在堆技术债。

**接受 AI 代码前的四问**（任一"不能"就记账）：
1. 不看代码，能画出它的流程图吗？
2. 能说出它故意没做什么吗？
3. 能构造一个让它失败的输入吗？
4. 删掉它，能重写出来吗？
