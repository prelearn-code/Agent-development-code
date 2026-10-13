# 代码布局与逐步扩展

V0–V6是交付顺序，16目标与M任务前缀用于验收索引。当前布局数据在[layout.json](layout.json)，`scripts/selftest.py --stage V1`检查当前目录和本文覆盖；未来模块仍保留位置，不要求第一天实现。工程字段以同级指南[V1工具合同](../../Agent-development-doc/stages/V1-CORE-DEMO.md#contract-4)与[V2数据库合同](../../Agent-development-doc/stages/V2-WEB.md#contract-3)为准。

## 1. 先关注核心文件

```text
packages/
  app/cli.py                  已实现薄入口，调用本人runner一次
  core/                       现有模型/配置/异常/日志
  crypto/providers/           待实现固定OpenSSL/GmSSL适配
  security/                   待实现本人定义的授权边界
  llm/                        待实现Ollama/NDJSON客户端
tools/
  builtin/                    待实现证书/摘要handler
  registry.py                 后续本人确定工具注册
  executor.py                 后续本人确定唯一授权执行入口
minimal_agent/
  runner.py                   后续本人手写，当前不存在
  traces/                     脱敏原始调用证据
tests/                        已有入口测试，后续增加合同/集成
```

第一条业务：直接摘要→registry/execute_tool→单tool反馈→本人有限Loop形成Demo，再添加证书工具。没有业务代码时`run`报未实现；不返回伪造证书、摘要或成功。启动合同见[CORE-FIRST](CORE-FIRST.md)，详细实现目标与标准见[V1阶段](../../Agent-development-doc/stages/V1-CORE-DEMO.md)。

## 2. 保留的目录与引入时机

| 目录 | 首次阶段 | 职责 |
|---|---|---|
| `packages/app/` | V0 | 薄CLI入口，仅调用学习者入口一次 |
| `packages/core/` | V0 | 现有类型、配置、异常、日志 |
| `scripts/` | V0 | 骨架、分层、配置自检 |
| `tests/` | V0 | 入口与合同测试 |
| `docs/decisions/` | V0 | 本人决策记录 |
| `packages/llm/` | V1 | Ollama原生客户端与NDJSON，待实现 |
| `packages/security/` | V1 | 本人定义授权边界，待实现 |
| `packages/crypto/providers/` | V1 | 固定OpenSSL/GmSSL适配，待实现 |
| `tools/builtin/` | V1 | 先inspect_certificate和digest_file，待实现 |
| `tools/tests/` | V1 | 工具正常/失败/边界验证，待实现 |
| `minimal_agent/` | V1 | 本人手写runner.py与Loop，待实现 |
| `minimal_agent/traces/` | V1 | 脱敏原始消息与调用证据 |
| `packages/db/` | V2 | 持久任务/资源/审计，待实现 |
| `packages/db/repository/` | V2 | 短事务与资源查询，待实现 |
| `packages/db/queries/` | V2 | 基础查询，V6补六查询 |
| `services/agent_api/routers/` | V2 | 合法Python包名，JSON API先行 |
| `web/src/` | V2 | 基础React网页，V6补专项 |
| `infra/` | V2 | 按需Compose/迁移/网络 |
| `mcp_integration/client/` | V3 | MCP桥接，待实现 |
| `mcp_integration/common/` | V3 | MCP协议适配与来源记录 |
| `mcp_integration/server_crypto/` | V3 | 先一个Crypto Server复用业务服务 |
| `graph/nodes/` | V4 | 本人State设计，审批与恢复，待实现 |
| `verifier/checks/` | V4 | 本人写状态检查，V5完整事实/引用 |
| `verifier/tests/` | V4 | 本人Verifier反例，待实现 |
| `pipelines/ingest/` | V5 | Parse/Chunk/索引发布，待实现 |
| `pipelines/retrieval/` | V5 | 授权检索与消融，待实现 |
| `pipelines/citation/` | V5 | 版本化定位/引用，待实现 |
| `memory/` | V5 | 来源/纠正/删除/隔离，待实现 |
| `eval/datasets/` | V6 | 小case持续积累，正式规模/冻结V6 |
| `mcp_integration/server_fs/` | V6 | 受控文件职责，待实现 |
| `mcp_integration/server_db/` | V6 | 固定元数据查询职责，待实现 |
| `services/agent_worker/` | V6 | 需要独立worker时实现，否则注明不适用 |


MCP项目包名为`mcp_integration`，SDK仍用`import mcp`；无需根目录自建`mcp`包。服务包采用`agent_api/agent_worker`合法名称，未来补__init__与实现时同步打包入口。当前`packages/app`不导入未来API/Graph/MCP，早期启动不依赖全套服务。

## 3. 依赖方向

```text
packages/app（入口适配） / services（API、可选worker）
                     ↓
          minimal_agent / graph（本人控制流）
                     ↓
       tools / mcp_integration / pipelines / memory / verifier
                     ↓
       packages/crypto / packages/security / packages/db / packages/llm
                     ↓
                   packages/core
```

core不导入app、业务、服务或存储；llm不依赖工具/图/DB；db不依赖控制流；crypto不依赖模型/Loop/UI。Provider操作由固定适配器完成，模型只提交授权ID；模型提出调用必须通过唯一execute_tool。MCP Server复用同业务服务并复查服务端权限/审批。

AST护栏检查普通绝对/相对import，动态加载需人工审查。`packages/app`唯一固定动态加载是学习者`minimal_agent.runner`，不接受模型或CLI传入任意模块路径。此薄适配器只调用一次，控制Loop由本人负责。

## 4. 命名、安装与完成状态

当前保留`packages/core`与现有类型/配置，不为了统一目录先搬到src/lpa。未来成熟后迁移须同步导入/打包/测试/指南，并保留运行证据。当前wheel包含核心及入口、tools、minimal_agent；扩展模块真正实现时再检查安装后的包与服务命令，不把占位目录当已打包功能。

clone后.gitkeep保证空位置存在；V6仍可不引入独立worker，但必须注明并发/队列不适用，不豁免单进程审批/恢复。布局自检绿不等于技术表通过。源码四仓库同级，Ubuntu运行、Windows访问页面，D盘本次修改与业务运行位置区分。
