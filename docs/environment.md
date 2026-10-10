# 环境实测记录

> 依据：指南 [01-ENVIRONMENT.md](../../Agent-development-doc/01-ENVIRONMENT.md) §8。
> **环境改变必须建新实验，不修改旧结果。**
> 全部数值在 **Ubuntu 内**取得；Windows 只是浏览器客户端，不产生环境数值。

## 主机（2026-10-10 实测，均取自 Ubuntu）

| 项 | 值 |
|---|---|
| CPU / 线程 | Intel Core i5-14600KF，`nproc` = 20 |
| RAM（Ubuntu 可见） | 15 GiB（宿主 31.8 GB，WSL 限额） |
| GPU | NVIDIA GeForce RTX 5060 Ti，16311 MiB |
| 驱动 | 591.86（CUDA Version 13.1 —— 仅为驱动支持上限） |
| GPU 空闲占用 | 2622 MiB（桌面常驻），**可用约 13.4 GB** |
| 内核 | 6.6.87.2-microsoft-standard-WSL2 |
| 发行版 | Ubuntu 22.04.5 LTS |
| 磁盘 | `/` = 1007 GB，可用 750 GB |
| 用户 | `zsw`（非 root） |
| Ubuntu 地址 | `172.26.9.67/20`（eth0，WSL 重建后会变） |

## 工具链（全部在 Ubuntu 内）

| 项 | 值 | 状态 |
|---|---|---|
| Python（Ubuntu 系统） | 3.10.12 | 项目要 3.12，由 uv 提供 |
| uv | `/home/zsw/.local/bin/uv`，0.11.12 | 已装 |
| **Ollama** | `/usr/local/bin/ollama`，v0.32.15 | **systemd 服务 enabled 且运行中**，`127.0.0.1:11434` |
| Ollama 模型目录 | `/usr/share/ollama/.ollama/models` | 20 GB |
| **Docker** | Ubuntu 内**原生** 29.1.3 | `overlay2` + cgroup v2 + seccomp |
| docker compose | **缺失** | 需 `docker-compose-plugin`，M1 前必修 |
| Docker Desktop | **未安装，也不需要** | 全部在 Ubuntu 原生 engine 上 |
| GPU 直通 | Ubuntu 内 `nvidia-smi` 可见 RTX 5060 Ti | 可用 |
| PyTorch | 未安装 | M3 后段 |
| Node.js / pnpm | v22.23.2 / 12.3.4（Ubuntu 内） | M6 前端 |

## 模型（Ollama，服务与模型都在 Ubuntu 内）

| 模型 | family | 参数 | 量化 | 体积 | 计划关系 |
|---|---|---|---|---|---|
| `qwen3.8:27b-q4_K_M` | qwen35 | 27.3B | Q4_K_M | 16.52 GB | 与计划模型**不同代** |
| `qwen3.8-agent-32k` | qwen35 | 27.3B | Q4_K_M | 16.52 GB | 自定义微调，非对照基线 |
| `qwen3-vl:4b` | qwen3vl | 4.4B | Q4_K_M | 3.07 GB | 视觉模型，不能当 Controller |
| **`qwen3:4b`** | — | — | — | — | **Phase 0 待拉取** |
| `bge-m3` | — | — | — | — | M3 待拉取 |

**警告**：现有 27B 模型体积 16.52 GB > 可用显存 13.4 GB，必然 CPU offload；
且与 `qwen3:4b/8b` 不同代，**不能用于 §13 的 4B vs 8B 对比结论**。

## 关键决策

| 决策 | 选择 | 理由 | 何时重新考虑 |
|---|---|---|---|
| 实现边界 | **全部在 Ubuntu 内** | sandbox 需要 Linux namespace/cgroup；Windows 侧无对等替代 | 不需要重考虑 |
| 仓库位置 | Ubuntu ext4 `/home/zsw/work/agent_development/Agent-development-code` | `/mnt/c`、`/mnt/d` 走 9P，venv 大量小文件慢数倍 | 不需要重考虑 |
| Ollama 位置 | **Ubuntu 内 systemd 服务** | 应用与模型回环通信；宿主 IP 漂移与跨系统网络故障点消失 | 不需要重考虑 |
| Ollama 监听 | `127.0.0.1:11434`（不对内网开放） | 没有跨系统调用需求；容器需要时用 `network_mode: host` | 若容器必须独立网络，改为监听 docker0 地址 |
| 交付形态 | **前端页面**，Windows 浏览器网络访问 | 评审只需一个页面，不需要在 Windows 装环境 | 不需要重考虑 |
| 对外端口 | 仅前端/API 监听 `0.0.0.0` | 其余服务保持回环，缩小攻击面 | 若需公网暴露则加反向代理与鉴权 |
| Docker 形态 | Ubuntu 内**原生**，不装 Desktop | 少一层转发，compose 行为与 Linux 服务器一致；M6 部署验收更真实 | 不需要重考虑 |
| 配置对齐 | `.env.example` ↔ `Settings` 双向校验 | 防止"文档有、代码没有" | 不需要重考虑 |

## 尚未完成（Phase 0 缺口）

- [ ] `qwen3:4b` 拉取
- [ ] Ubuntu 侧 `docker-compose-plugin`
- [ ] `uv venv --python 3.12` + `uv sync --extra m1 --extra dev`
- [ ] 一个通过的最小请求测试

**已消除的旧缺口**：Ollama CLI 与服务已在 Ubuntu 内就绪；不再需要 Windows 侧
`OLLAMA_HOST=0.0.0.0` 与入站防火墙规则；不再需要查找宿主 IP。
