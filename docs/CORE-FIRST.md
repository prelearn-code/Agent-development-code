# 先写一条可运行的核心链

当前CLI已经能启动与报告状态，真实密码工具、执行器、LLM客户端和Loop尚未实现。本文件给你先动手的范围，完整技术标准仍见[00](../../Agent-development-doc/00-ROADMAP.md)与[05](../../Agent-development-doc/05-UBUNTU-STEP-BY-STEP.md)。

## 1. 当前可执行与待实现

| 内容 | 状态 | 能证明什么 |
|---|---|---|
| core类型/配置/日志 | 已有骨架 | 稳定接口，业务限制还需逐项实现 |
| `python -m packages.app status` | 可运行 | 命令入口和本人runner文件存在性，不请求网络 |
| `python -m packages.app run --question ...` | 适配器可运行 | runner缺失明确退出2；完成后固定调用本人入口一次 |
| crypto/tools/llm/executor | 待实现 | 写完并独立验证才能用 |
| minimal_agent/runner.py | 本人手写，当前不存在 | 消息反馈、Loop停止/预算/失败须本人掌握 |
| MCP/API/Graph/知识与前端 | 保留扩展位置 | 按V2–V6开放，不阻塞最初核心 |

## 2. V1具体写文件的顺序

| 顺序/任务 | 文件或职责 | 本人必须做到 | 独立证据 |
|---|---|---|---|
| 1 M1 01 | 阅读packages/core/models.py | 解释ToolCall/ToolSpec/ToolResult及空结果成功、错误类型 | 正常/空/失败序列化说明 |
| 2 M1 02–03 | packages/crypto/providers/openssl_cli.py | 固定程序/参数，直接解析公开证书/计算摘要；超时清理 | CLI/已知向量对照与真实版本 |
| 3 M1 02–05 | tools/builtin/inspect_certificate.py、digest_file.py | 结构化输入输出，资源ID服务端解析，异常分类/日志脱敏 | 正常/坏输入/资源拒绝，不显示秘密 |
| 4 M1 04 | tools/registry.py、executor.py；packages/security | 本人定义参数/归属/允许范围，唯一execute_tool入口 | 未知工具、非法/越权拒绝且adapter未调用 |
| 5 M1 07 | tools/tests/ | 先只读行为独立验证；写操作到V4再补 | 实际断言，不靠测试数量 |
| 6 M1 08–10 | packages/llm/client.py | 非流式请求，保存原生tool_calls与真实tool反馈 | 原始消息逐条说明 |
| 7 M1 11–13 | minimal_agent/runner.py | 本人手写有限Loop、停止原因、预算与NDJSON | 单/多调用、失败、重复、超预算Trace |
| 8 V1出口 | 通过已有app入口运行 | 相同question调用本人run一次，最终JSON绑定实际结果 | 自己改一需求/排错后回归 |

V1先两个只读工具，AEAD练习M1 06到V4。GmSSL先能力核对与SM3补齐，暂时不可用明确记录，不伪装成OpenSSL同名结果。固定profile、key/nonce/写审批等在开放写工具前完成，不能提前裸加密。

## 3. 入口合同，不提供Loop实现

本人创建`minimal_agent/runner.py`，暴露如下签名（只是接口）：

```python
async def run(*, question: str) -> dict[str, object]:
    ...
```

返回一个JSON对象，可含run_id/status/answer和脱敏结果引用；所有内部值可序列化，不放密钥/口令/明文/原始异常。字段按已实现Run合同固定，调用成功不等于任务成功。CLI不迭代模型、不选择工具、不自动重试；它只加载固定module、await一次并输出JSON。

V1命令入口用于教学单用户；V2服务端创建Run并鉴权后，需要按实际接口补可信运行上下文。身份/归属不从question中的user_id或角色字符串取得；扩展参数时保持原CLI的question关键字可用并同步合同测试。

| 退出码 | 含义 |
|---|---|
| 0 | status报告或本人函数正常返回JSON；业务成功还需看状态/实际资源 |
| 2 | 参数无效或本人runner尚未创建 |
| 3 | 依赖/入口加载/执行/输出失败，返回稳定错误码，不打印原始异常 |
| 130 | 用户中断 |

运行命令：

```bash
python -m packages.app status
python -m packages.app run --question '检查授权教学证书的有效期'
```

未创建runner时第二条应失败，不用空回答使它看似通过。依赖缺失与加载错误按error区分，在自己的测试和脱敏日志定位；不把异常/配置秘密粘给模型。

## 4. 保持当前类型，登记后续差异

ToolSpec目前是name/retry，ToolResult是citations；目标version/idempotent/通用evidence_refs按指南结构文档§4.1逐步迁移，不要求第一天重写成熟接口。Citation旧页码说明不能作为±1统一容差的验收规则，实际定位按版本/真实区间；DEFAULT_POLICY是教学起点，破坏操作仍按业务范围默认禁止，不能直接将枚举策略当资源授权。

先完成真实工具，再工具反馈，再本人Loop。AI可以做入口/样板与审查，核心Loop、Verifier/对抗测试、个人ADR本人写，State和安全边界本人设计。目录占位、入口status或本次单元测试不签收这些业务目标。

## 5. 后续逐步补充

V2接JSON API/DB/基础React页；V3用mcp_integration/server_crypto复用工具并直调对照；V4加固定审批/账本/一种加解密与最小Graph恢复；V5加RAG/Verifier/Memory/SSE；V6补轮换/CSR/测试签发、三职责MCP、实验/安全/完整UI/部署。每次复用已验证下层，不为下一框架重写当前Loop。
