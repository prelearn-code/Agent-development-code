# AI协作与阶段要求

以同级[AI协作原则](../Agent-development-doc/reference/07-AGENT-SYSTEM-DESIGN.md#ai-assistance)、[学习总览](../Agent-development-doc/LEARNING-PATH.md)和[当前阶段](../Agent-development-doc/stages/V1-CORE-DEMO.md)为依据，验收包含人的解释、独立修改、排错与真实证据。

## 0. 当前授权与执行位置

本次只修改`D:\work\Agent-development-code`并更新远端；**不得直接读写、拉取、安装或运行用户的WSL仓库**，WSL由用户自行同步。未来仅按人明确指定的仓库操作。学习项目的模型/密码业务、依赖构建与服务运行仍安排在Ubuntu；D盘骨架/单元检查不冒充Ubuntu业务验收。

## 1. 本人完成的核心

| 内容 | 位置 | AI边界 |
|---|---|---|
| 手写Agent Loop | minimal_agent/runner.py | 本人编写，AI仅审查；不能用完整示例/框架替代 |
| Verifier核心与对抗性测试 | verifier/checks、verifier/tests | 本人编写，AI仅审查 |
| 个人决策记录 | docs/decisions | 本人判断与证据，AI仅审查 |
| 安全判断/状态机 | security/tools/graph | 本人定边界与State，AI审查或按已确定接口填样板 |

薄CLI启动、固定入口加载、序列化与样板测试允许AI协助；必须清楚区分一次入口调用与Loop控制逻辑。不修改/放宽已有正确测试或gold来迎合结果。错误断言修订需依据、人工审查、新数据版本与重跑；安全注入用例由本人设计。

## 2. 只沿V顺序增加功能

V0环境→V1只读核心/本人Loop→V2第一网页→V3一个Crypto MCP→V4固定审批/恢复→V5知识与可靠性→V6完整实验/交付。目标编号与M任务前缀是稳定索引，依赖组名m1–m4不是执行阶段。先单摘要工具Demo，再扩展两只读工具，不开放任意shell/SQL/路径；新功能按当前切片开放，不为后续占位模块提前装全服务。

V交付通过不自动签收技术全表，40技术表和81详细任务要求保持；专项标签条件见学习总览。前端也是目标15：允许AI样板，学习者须理解接口、异步、审批、刷新/断线与安全渲染，并自己改交互与排错。

## 3. 接受与提交前检查

```text
[ ] 检查diff、测试/gold变化与影响范围
[ ] selftest --stage 当前V --strict；pytest真实运行
[ ] 改动文件ruff/type检查；记录已有基线问题，不用新改动扩大重构
[ ] Prompt/模型/工具/检索/流程改变按02第9–10节相关回归
[ ] 当前切片正常/失败/权限与真实副作用证据；未跑标未验证
[ ] 本人解释、需求修改/排错；关键to-digest消化
```

普通合同/mock检查与专用Ollama/GPU/frozen评测分开。早期缺正式数据不捏造指标，用审定小case；V6补完整规模。实际越权任一失败阻止交付。模型比较固定环境/数据，阈值用pp并结合样本量/逐case/区间，不能机械套未审定的2pt。

## 4. 工程合同

- 保留packages/core成熟类型；core不导入app/业务/存储，依赖方向见STRUCTURE，自检查普通绝对/相对import。
- ToolResult用Pydantic泛型、容器默认工厂，空结果success=True；预期业务失败结构化，意外异常由execute_tool分类，取消正确传播。
- 模型工具调用仅走execute_tool，资源由可信身份/服务端ID解析；read_only=False保持retry=0。默认Policy不替代真实授权/审批。
- 配置字段变更同步Settings与.env.example；不提交真实.env、材料、解密内容或日志，脱敏使用现有scrub。
- 原生Ollama非流式先做，再NDJSON；前端V2 JSON/快照、V5 SSE，两套流解析分开。tool反馈遵守锁定版本实际报文。
- 项目模块mcp_integration，第三方SDK仍mcp；stdout协议/stderr日志。Server复查本地权限与固定审批，不信任模型approved或annotation。
- secrets/明文不进模型、State、ToolResult或浏览器日志。布局检查不是完整安全证明，动态导入/外部副作用需审查。
- packages/app只加载固定minimal_agent.runner并调用一次，禁止加入规划、工具选择、循环或自动批准。

## 5. 命令与理解记录

```bash
python3 scripts/selftest.py --stage V1 --strict
python -m pytest -q
python -m ruff check packages/app tests/test_entry.py scripts/selftest.py
python -m mypy packages/app
```

新增业务跑其相关单元/集成/Provider与失败验证；全仓lint/type已知基线缺口如实记录。to-digest空可以表示已理解，不代表自欺；不断增长要安排消化。本阶段关键协议/安全项不能延期，其余按计划期限补齐。ADR本人写，不能为提交由AI编理由。
