# Crypto Agent

本项目通过模型理解用户请求，使用 MCP 工具调用已编译的 OpenSSL / GmSSL 可执行程序，并将真实结果反馈给模型。

最小 Agent Demo 的已有功能已迁入主项目：`packages/app/agent.py`保留有限 Loop 与终端交互，模型请求、工具校验、MCP 连接、SM2 程序调用和工具注册分别放在对应模块。后续直接在这些模块完善。

## 目录结构

下面列出实际源代码与模块骨架。标注“待实现”的 Python 文件只保留模块说明，没有业务实现。运行数据目录由本地运行创建，不随 Git 保存。

```text
Agent-development-code/
├── README.md                              # 项目说明与目录结构
├── AGENTS.md                              # AI 协作与实现边界
├── pyproject.toml                         # 依赖、打包、检查与 CLI 配置
├── uv.lock                                # 实际依赖锁
├── .env.example                           # 配置样例
├── .gitignore
├── .gitattributes
├── packages/                             # 可复用部件
│   ├── __init__.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py                         # 单次请求 CLI 入口
│   │   └── agent.py                       # 已有 Loop 与交互入口
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py                      # ToolCall / ToolSpec / ToolResult
│   │   ├── config.py                      # Settings
│   │   ├── errors.py                      # 错误类型
│   │   └── logging.py                     # 日志与脱敏
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py                      # 已有 Ollama 非流式请求
│   │   └── streaming.py                   # 待实现：原生 NDJSON
│   ├── crypto/
│   │   ├── __init__.py
│   │   ├── keystore.py                    # 已有教学 SM2 密钥生成与查找
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── gmssl_cli.py               # 已有 SM2 GmSSL CLI 固定调用
│   │       └── openssl_cli.py             # 已有 OpenSSL SHA-256 固定调用
│   ├── security/
│   │   ├── __init__.py
│   │   ├── policy.py                      # 待实现：本地操作规则
│   │   ├── resources.py                   # 待实现：资源归属与路径检查
│   │   └── approvals.py                   # 待实现：审批绑定与校验
│   └── db/
│       ├── __init__.py
│       ├── models.py                      # 待实现：数据库模型
│       ├── session.py                     # 待实现：连接与短事务
│       ├── migrations/                    # 应用数据库迁移
│       ├── repository/                    # 资源与任务读写接口
│       └── queries/                       # 固定查询
├── tools/
│   ├── __init__.py
│   ├── registry.py                        # 已有发现工具的参数校验
│   ├── executor.py                        # 已有 MCP 调用与结果处理
│   ├── builtin/                           # 按需使用的本地工具
│   └── tests/                             # 工具测试
├── mcp_integration/
│   ├── __init__.py
│   ├── client/
│   │   ├── __init__.py
│   │   ├── connection.py                  # 已有 stdio 连接生命周期
│   │   └── bridge.py                      # 已有工具发现与 schema 转换
│   ├── common/
│   │   ├── __init__.py
│   │   └── mapping.py                     # 待实现：协议与工具身份映射
│   ├── server_crypto/
│   │   ├── __init__.py
│   │   ├── server.py                      # 当前 Crypto MCP 服务入口
│   │   ├── gmssl_tools/
│   │   │   ├── __init__.py
│   │   │   └── sm_tools.py                # 已有 SM2 工具包装与注册
│   │   └── openssl_tools/
│   │       ├── __init__.py
│   │       └── tools.py                   # 已有 SHA-256 MCP 工具包装与注册
│   ├── server_fs/                         # 后续受控文件 MCP 服务
│   └── server_db/                         # 后续固定查询 MCP 服务
├── graph/
│   ├── __init__.py
│   └── nodes/                             # 本人定义的审批与恢复节点
├── pipelines/
│   ├── __init__.py
│   ├── ingest/                            # 解析、分块、索引发布
│   ├── retrieval/                         # 授权检索、融合、重排
│   └── citation/                          # 来源、版本与引用定位
├── memory/                               # 跨会话记忆
├── verifier/
│   ├── checks/                            # 本人实现的结果检查
│   └── tests/                             # 本人设计的验证与反例测试
├── services/
│   ├── agent_api/
│   │   ├── __init__.py
│   │   ├── main.py                        # 待实现：API 应用组装
│   │   └── routers/                       # 上传、Run、审批、产物等接口
│   └── agent_worker/                      # 按需引入后台执行进程
├── web/
│   └── src/                               # 后续前端工程
├── infra/
│   ├── dockerfiles/                       # 镜像构建
│   └── init/                              # 服务首次初始化
├── eval/
│   ├── __init__.py
│   ├── datasets/                          # 固定场景与期望结果
│   └── runner.py                          # 待实现：评测执行
├── reports/                              # 报告与图表
├── tests/
│   ├── test_entry.py
│   ├── test_layout_contract.py
│   ├── test_agent.py
│   ├── test_crypto_config.py
│   ├── test_llm_config.py
│   ├── test_sm2_mcp.py
│   └── test_sha256_mcp.py
├── scripts/
│   ├── selftest.py                        # 布局、配置与分层检查
│   └── layout.json                        # 阶段目录契约
├── data/                                  # 按 file_id 存放输入与密码产物，Git忽略
└── keys/                                  # 按 key_id 存放教学密钥，Git忽略
```

Graph State / workflow、数据库迁移配置、前端 `package.json` 与 Compose 配置仍按后续功能引入。

以后新增的输入文件和密码产物统一放在项目根目录的 `data/<file_id>/`，不再按 SM2 等算法增加目录层级；教学密钥放在 `keys/<key_id>/`，算法记录在各密钥目录的 `metadata.json` 中。两个根目录均被 Git 忽略。旧的 `data/SM2/<file_id>/` 数据不会自动迁移；若需继续通过 MCP 使用，应将相应的 `<file_id>` 文件夹移至 `data/`。

`key_id` 使用 `<算法小写>_<32位十六进制ID>`，例如 `sm2_` 加 32 位 ID。查找时以完整 `key_id` 作为目录名，并检查 `metadata.json` 的 `key_id` 与算法（如 `SM2`）和入参一致；不再支持 `default` 等配置别名。私钥、公钥和口令文件是否可用由具体工具或 Provider 检查。

## 模块职责

| 目录 | 职责 |
|---|---|
| `packages/app/` | 已有 Agent Loop、终端交互和单次请求 CLI |
| `packages/core/` | 共同类型、配置、错误、日志 |
| `scripts/` | 目录契约与开发检查 |
| `tests/` | 入口、合同、跨模块与 MCP 集成测试 |
| `packages/llm/` | 模型请求、响应与 NDJSON |
| `packages/security/` | 本地授权、资源与审批检查 |
| `packages/crypto/providers/` | 已有 GmSSL SM2 与 OpenSSL SHA-256 固定调用 |
| `tools/builtin/` | 按需增加的本地工具，不重复实现同一套 MCP 密码能力 |
| `tools/tests/` | 工具登记、校验与执行行为测试 |
| `packages/db/` | 数据库模型与事务 |
| `packages/db/migrations/` | 应用 schema 迁移 |
| `packages/db/repository/` | 资源、Run、审批与审计读写 |
| `packages/db/queries/` | 固定业务查询与统计 |
| `services/agent_api/routers/` | HTTP 接口 |
| `web/src/` | 前端页面、API 通信与状态 |
| `infra/` | 部署配置 |
| `infra/dockerfiles/` | 进程镜像构建 |
| `infra/init/` | 服务首次初始化 |
| `mcp_integration/client/` | MCP 连接、工具发现与调用 |
| `mcp_integration/common/` | 协议转换与来源映射 |
| `mcp_integration/server_crypto/` | Crypto MCP 服务组装 |
| `mcp_integration/server_crypto/gmssl_tools/` | GmSSL MCP 工具包装与注册 |
| `mcp_integration/server_crypto/openssl_tools/` | OpenSSL MCP 工具包装与注册 |
| `graph/nodes/` | 审批、执行、验证与恢复节点 |
| `verifier/checks/` | 本人实现的状态、事实与引用检查 |
| `verifier/tests/` | 本人设计的 Verifier 测试 |
| `pipelines/ingest/` | 知识解析、分块与索引发布 |
| `pipelines/retrieval/` | 授权检索与重排 |
| `pipelines/citation/` | 来源版本与引用定位 |
| `memory/` | 可追溯、可纠正的长期记忆 |
| `eval/datasets/` | 评测场景与固定期望 |
| `mcp_integration/server_fs/` | 后续受控文件服务 |
| `mcp_integration/server_db/` | 后续固定查询服务 |
| `services/agent_worker/` | 按需增加的后台任务进程 |
| `reports/` | 面向人的报告与图表 |

正式模块的目标调用链：

```text
模型工具提议 → tools/executor → MCP Client → MCP 工具
                                             ↓
                                  crypto/providers 中的函数
                                             ↓
                                  编译好的 openssl / gmssl
```

MCP 工具负责参数、资源校验、产物保存与返回结构；Provider 负责固定命令、超时和后端结果解析。每次计算仍执行可执行程序。服务端复查自己的权限边界，annotations 只是行为提示。

`tools/` 已实现发现工具的参数校验、`ToolSpec` 规格表、资源边界与风险策略，并由 `executor` 作为唯一执行入口调用 MCP；预算/超时/Trace 留在 04 段。模型客户端只发送请求，当前 Loop 负责组织消息与工具反馈。

## 运行当前 Demo

要求项目 Python >= 3.12、锁定依赖、可用的 Ollama 服务和本地 GmSSL 可执行程序。从代码仓库根目录执行：

```bash
uv sync --frozen --extra m1 --extra dev
.venv/bin/python -m packages.app.agent
```

默认模型为 `qwen3.5:4b`，地址为 `http://127.0.0.1:11434`。交互入口可通过 `--model`、`--base-url` 修改；模型请求超时由 `LLM_TIMEOUT_S` 控制。入口会自动启动当前 stdio MCP 服务。

模型请求使用 HTTPX `AsyncClient`，`packages.llm.client.call_model()` 是异步函数，调用时使用 `await`。入口通过 `create_model_client()` 在单次任务或整个交互会话中复用连接池，并在退出时关闭；独立调用 `call_model()` 时也会自行创建和关闭连接。请求仍使用 Ollama 原生非流式 `/api/chat` 格式。MCP 连接使用 SDK 2.x 的 `Client` 管理初始化与关闭，工具调用仍统一经过 `tools/executor.py`。核心 `ToolResult[T]` 使用 Python 3.12 泛型语法，字段与 JSON 格式保持原契约。

密码工具的路径和执行限制统一由 `packages/core/config.py` 中的 `Settings` 管理。需要改动时，把 `.env.example` 复制为项目根目录的 `.env`，只填写要覆盖的配置项；环境变量优先于 `.env`，修改后重启 Agent/MCP 服务。相对路径均以代码仓库根目录为基准，启动命令所在目录不会改变它们。

| 配置项 | 默认值 | 作用 |
|---|---|---|
| `CRYPTO_KEY_ROOT` | `keys` | `key_id` 对应的密钥根目录；已有目录须仅属主可访问 |
| `CRYPTO_DATA_ROOT` | `data` | `file_id` 对应的文件根目录 |
| `GMSSL_BIN` | `../.local/gmssl/bin/gmssl` | GmSSL 可执行文件 |
| `OPENSSL_BIN` | `/bin/openssl` | OpenSSL 可执行文件 |
| `CRYPTO_MAX_FILE_BYTES` | `104857600` | 签名和 SHA-256 的最大输入字节数 |
| `CRYPTO_TIMEOUT_S` | `10` | 单次密码命令的超时秒数 |

例如在 `.env` 中写入 `CRYPTO_KEY_ROOT=/srv/agent/keys`、`CRYPTO_DATA_ROOT=/srv/agent/files`，服务就会按这些目录解析 `key_id` 和 `file_id`。这两个目录仍由服务端管理，不由模型传入任意路径。默认情况下，SM2 文件工具使用 `file_id` 定位 `data/<file_id>/` 中的唯一原始输入文件，使用 `key_id` 定位 `keys/<key_id>/` 中的密钥；算法保存在密钥目录的 `metadata.json`。签名结果保存为 `signature.der`；SM2 公钥加密单次最多处理 255 字节，结果保存为 `ciphertext.der`。`sm2_dec` 使用对应私钥解密该密文，结果以权限 `0600` 保存为同目录的 `decrypted.bin`，MCP 只返回文件名，不返回明文。服务端通过 GmSSL 的 `-in`/`-out` 处理文件，写操作成功后才发布结果文件。`sha256_file(file_id)` 使用配置的 OpenSSL 对同一目录中的唯一原始文件计算 SHA-256，返回十六进制摘要，不返回文件内容。当前密钥生成、签名和加解密沿用教学 Demo 的行为。02–04 段 MCP 只暴露只读工具（`sha256_file`、`sm2_verify_signature`），写工具 06 段再恢复注册。

单独启动服务：

```bash
.venv/bin/python -m mcp_integration.server_crypto.server
```

该命令使用 stdio MCP 协议，供 MCP 客户端连接。

单次请求 CLI 可检查入口并运行已有 Agent：

```bash
.venv/bin/python -m packages.app status
.venv/bin/python -m packages.app run --question '验证 file_001 的签名'
```

`packages.app run` 和 `crypto-agent run` 调用`packages.app.agent.run`执行一轮请求并返回JSON。交互入口负责多轮会话；单次入口仍复用同一`chat_turn`实现。

## 检查与扩展

```bash
.venv/bin/python scripts/selftest.py --stage V3 --strict
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check packages/app scripts/selftest.py tests/test_entry.py tests/test_layout_contract.py
.venv/bin/python -m mypy packages/app scripts/selftest.py
```

`scripts/layout.json` 记录 V0–V6 的目录引入阶段；自检同时检查 README 中的目录职责。目录与模块骨架存在不代表业务完成。SM2 集成测试需要本地 GmSSL 和系统 OpenSSL，缺失时跳过相关测试；pytest 不调用真实 Ollama。

每个新部件先独立验证，再由 Demo 调用，逐步移除重复实现。实际启用新的包、命令或依赖时，同步打包配置、依赖锁和相关测试。输入、密钥、解密产物与运行日志不提交 Git；业务结果使用受控引用，密码材料不进入模型上下文。
