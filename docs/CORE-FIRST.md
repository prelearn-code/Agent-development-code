# 先写一条可运行的核心链

当前CLI已经能启动与报告状态，真实密码工具、执行器、LLM客户端和Loop尚未实现。本文件给你先动手的范围，完整目标、技术标准和步骤集中在[V1阶段指南](../../Agent-development-doc/stages/V1-CORE-DEMO.md)；全程顺序见[Roadmap](../../Agent-development-doc/ROADMAP.md)。

## 1. 当前可执行与待实现

| 内容 | 状态 | 能证明什么 |
|---|---|---|
| core类型/配置/日志 | 已有骨架 | 稳定接口，业务限制还需逐项实现 |
| `python -m packages.app status` | 可运行 | 命令入口和本人runner文件存在性，不请求网络 |
| `python -m packages.app run --question ...` | 适配器可运行 | runner缺失明确退出2；完成后固定调用本人入口一次 |
| crypto/tools/llm/executor | 待实现 | 写完并独立验证才能用 |
| minimal_agent/runner.py | 本人手写，当前不存在 | 消息反馈、Loop停止/预算/失败须本人掌握 |
| MCP/API/Graph/知识与前端 | 保留扩展位置 | 按V2–V6开放，不阻塞最初核心 |

## 2. 先完成摘要Agent Demo

按[V1第一个Demo](../../Agent-development-doc/stages/V1-CORE-DEMO.md#first-demo)执行：直接摘要 → 注册/校验 → 模型工具提议 → 真实结果反馈 → 本人有限Loop → CLI运行。先一个digest_file，摘要Demo通过后加inspect_certificate，最后补完整V1预算/多调用/NDJSON。详细任务和掌握标准只在阶段指南维护。

| 当前Demo职责 | 实现位置 |
|---|---|
| 固定OpenSSL摘要适配器 | packages/crypto/providers/openssl_cli.py |
| 摘要参数与结构化结果 | tools/builtin/digest_file.py |
| 固定工具注册、资源与参数校验、唯一执行入口 | tools/registry.py、tools/executor.py、packages/security |
| 正常与相关失败验证 | tools/tests/test_digest_file.py |
| 非流式模型请求/原生工具反馈 | packages/llm/client.py |
| 本人手写Loop及run入口 | minimal_agent/runner.py，当前不存在，AI只审查 |

AEAD、key/nonce/审批在V4；GmSSL先能力核对，后补SM3。未验证能力明确记录，不伪装成OpenSSL同名结果。

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
python -m packages.app run --question '计算教学文件 sample.txt 的 SHA-256 摘要'
```

未创建runner时第二条应失败，不用空回答使它看似通过。依赖缺失与加载错误按error区分，在自己的测试和脱敏日志定位；不把异常/配置秘密粘给模型。

## 4. 保持当前类型，登记后续差异

ToolSpec目前是name/retry，ToolResult是citations；目标version/idempotent/通用evidence_refs按[V1工程合同与当前类型映射](../../Agent-development-doc/stages/V1-CORE-DEMO.md#contract-4)逐步迁移，不要求第一天重写成熟接口。Citation旧页码说明不能作为±1统一容差的验收规则，实际定位按版本/真实区间；DEFAULT_POLICY是教学起点，破坏操作仍按业务范围默认禁止，不能直接将枚举策略当资源授权。

先完成真实工具，再工具反馈，再本人Loop。AI可以做入口/样板与审查，核心Loop、Verifier/对抗测试、个人ADR本人写，State和安全边界本人设计。目录占位、入口status或本次单元测试不签收这些业务目标。

## 5. 后续逐步补充

V2接JSON API/DB/基础React页；V3用mcp_integration/server_crypto复用工具并直调对照；V4加固定审批/账本/一种加解密与最小Graph恢复；V5加RAG/Verifier/Memory/SSE；V6补轮换/CSR/测试签发、三职责MCP、实验/安全/完整UI/部署。每次复用已验证下层，不为下一框架重写当前Loop。
