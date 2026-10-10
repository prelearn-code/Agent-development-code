# 环境实测记录

> 依据：指南 [01-ENVIRONMENT.md](../../Agent-development-doc/01-ENVIRONMENT.md) §8。
> **环境改变必须建新实验，不修改旧结果。**

## 主机（2026-10-10 实测）

| 项 | 值 |
|---|---|
| CPU | Intel Core i5-14600KF，14 核 / 20 线程（WSL 内 `nproc` = 20） |
| RAM | 31.8 GB |
| GPU | NVIDIA GeForce RTX 5060 Ti，16311 MiB |
| 驱动 | 591.86（CUDA Version 13.1 —— 仅为驱动支持上限） |
| GPU 空闲占用 | 2483 MiB（桌面常驻），**可用约 13.5 GB** |
| OS | Windows + WSL2 Ubuntu-22.04.5 LTS |
| WSL 磁盘 | `/` = 1007 GB，可用 750 GB |
| WSL 用户 | `zsw`（非 root） |
| WSL 网络 | **NAT 模式**（WSL→Windows 的 `localhost` 转发不可用） |

## 工具链

| 项 | 值 | 状态 |
|---|---|---|
| Python（WSL 系统） | 3.10.12 | 项目要 3.12，由 uv 提供 |
| Python（Windows） | 3.12.8 @ `D:\evm\python3.12.8` | 历史记录 |
| uv（WSL） | `/home/zsw/.local/bin/uv` | 已装 |
| **Ollama** | Windows 原生，API v0.32.15 | API 在跑；**CLI 不在 PATH** |
| **Docker** | WSL 内**原生** 29.1.3 | `overlay2` + cgroup v2 + seccomp |
| docker compose | **缺失** | 需 `docker-compose-plugin`，M1 前必修 |
| Docker Desktop | **未安装** | 有意不装，见决策记录 |
| GPU 直通（WSL） | `nvidia-smi -L` 可见 RTX 5060 Ti | 可用 |
| PyTorch | 未安装 | M3 后段 |
| Node.js | v24.11.1（Windows） | M6 前端 |

## 模型（Ollama）

| 模型 | family | 参数 | 量化 | 体积 | 计划关系 |
|---|---|---|---|---|---|
| `qwen3.8:27b-q4_K_M` | qwen35 | 27.3B | Q4_K_M | 16.52 GB | 与计划模型**不同代** |
| `qwen3.8-agent-32k` | qwen35 | 27.3B | Q4_K_M | 16.52 GB | 自定义微调，非对照基线 |
| `qwen3-vl:4b` | qwen3vl | 4.4B | Q4_K_M | 3.07 GB | 视觉模型，不能当 Controller |
| **`qwen3:4b`** | — | — | — | — | **Phase 0 待拉取** |
| `bge-m3` | — | — | — | — | M3 待拉取 |

**警告**：现有 27B 模型体积 16.52 GB > 可用显存 13.5 GB，必然 CPU offload；
且与 `qwen3:4b/8b` 不同代，**不能用于 §13 的 4B vs 8B 对比结论**。

## 关键决策

| 决策 | 选择 | 理由 | 何时重新考虑 |
|---|---|---|---|
| 仓库位置 | WSL ext4 `~/projects/Agent-development-code` | `/mnt/d` 走 9P，venv 大量小文件慢数倍 | 不需要重考虑 |
| Ollama 位置 | 保留 Windows 原生 | GPU 已生效、模型已下载；迁移需重拉 16.5GB | 若 WSL→Windows 网络持续不稳，则移入 WSL（GPU 直通已验证可用） |
| Docker 形态 | WSL 内**原生**，不装 Desktop | 少一层转发，compose 行为与 Linux 服务器一致；M6 部署验收更真实 | 若需与 Windows 文件系统深度集成 |
| Ollama 监听 | `0.0.0.0:11434` + 防火墙限源 | NAT 模式下 WSL 必须走宿主 IP | 若改用 mirrored 网络可回到 127.0.0.1 |
| 配置对齐 | `.env.example` ↔ `Settings` 双向校验 | 防止"文档有、代码没有" | 不需要重考虑 |

## 尚未完成（Phase 0 缺口）

- [ ] `qwen3:4b` 拉取
- [ ] Ollama CLI 可用（`winget install Ollama.Ollama` 会一并装）
- [ ] Windows 侧 `OLLAMA_HOST=0.0.0.0:11434` + 防火墙规则
- [ ] WSL 侧 `docker-compose-plugin`
- [ ] `uv venv --python 3.12` + `uv sync --extra m1 --extra dev`
- [ ] 一个通过的最小请求测试
