# Git 同步说明

> 两个仓库**独立管理、独立提交**。指南是"教材"，本项目是"作业"。

---

## 1. 两个仓库的关系

```
D:\work\
├── local-agent-learning-path\      仓库 A —— 指南（教材）
│   └── 相对稳定，改动少，主要在修订时提交
└── local-professional-agent\       仓库 B —— 实现（作业）
    └── 高频提交，按里程碑打 tag
```

**为什么分开**：

1. 指南里有指向 `../local-agent-learning-path/` 的相对链接，同目录结构下才能点开
2. 指南是别人（或你自己）写的规范，实现是你写的代码 —— 版本演进节奏完全不同
3. 如果合并成一个仓库，M1 的一个小改动会污染指南的提交历史

**代价**：新机器 clone 时**两个都要 clone**，且必须放在同级目录。
本文件的 §4 给出精确命令。

---

## 2. 仓库 A：指南

```bash
cd ~/projects
git clone <指南远端> local-agent-learning-path
cd local-agent-learning-path

# 提交前跑指南自带的三个检查
python3 eval/validate_dataset.py --all --mode draft
python3 -m unittest discover -s eval -p 'test_*.py' -v
python3 scripts/check_docs.py
```

**易踩的坑**：

- **不要用 PowerShell 的 `Get-Content | Set-Content` 改中文文档**。
  它会按 ANSI 读、按 UTF-8 写，中文全部变成 mojibake
  （历史上发生过一次，靠 `before-2026-10-10.zip` 恢复）。
  用 `git commit` 前的编辑器，或 Python 显式 `encoding="utf-8"`。
- `.gitignore` 已排除 `eval/results/`；`data/` 与 `.venv/` 同理。

---

## 3. 仓库 B：实现

```bash
cd ~/projects/local-professional-agent

# 提交前必须全绿
python3 scripts/selftest.py
uv run pytest -q
uv run ruff check .
```

**提交纪律**：

| 规则 | 原因 |
|---|---|
| `.env` 永不提交 | 含密钥；已在 `.gitignore` |
| 数据与产物（`data/`、`eval/results/`）不提交 | 体积大、含隐私 |
| 每个里程碑打 tag（`phase0-done`、`m1-tools-done` …） | 指南 `checklist.md` 按 tag 核对产物 |
| 决策记录与代码**同一次提交** | 保证"为什么"和"做了什么"可追溯 |
| `minimal_agent/` 的提交信息注明"手写" | 红线项，便于日后自查 |

**提交信息建议格式**：

```
<milestone>: <动词> <对象>

例：
m1: 实现 ToolResult 契约与非幂等重试守卫
m1: 手写 Agent Loop 的非流式路径 + 保存原始 NDJSON trace
docs: 记录为什么 Ollama 留在 Windows 宿主
```

---

## 4. 新机器部署（完整流程）

```bash
# 1. 目录结构必须同级，否则相对链接会断
mkdir -p ~/projects && cd ~/projects

# 2. 两个都 clone
git clone <指南远端>  local-agent-learning-path
git clone <实现远端>  local-professional-agent

# 3. 环境（详见 01-ENVIRONMENT.md）
sudo apt update && sudo apt install -y docker-compose-plugin
cd ~/projects/local-professional-agent
uv venv --python 3.12 .venv && source .venv/bin/activate
uv sync --extra m1 --extra dev
cp .env.example .env      # 改 OLLAMA_BASE_URL 为宿主 IP

# 4. 找到宿主 IP（WSL 重建后会变）
ip route show default | awk '{print $3}'

# 5. 验证
python3 scripts/selftest.py
uv run pytest -q
```

**Windows 侧需要做的一次性配置**（见 `docs/environment.md`）：

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_HOST','0.0.0.0:11434','User')
New-NetFirewallRule -DisplayName "Ollama for WSL" -Direction Inbound `
  -Protocol TCP -LocalPort 11434 -Action Allow -Profile Private
```

---

## 5. 远端选择

未指定远端时的建议：

| 仓库 | 建议 | 注意 |
|---|---|---|
| 指南 | 私有仓库 | 无隐私内容，但没必要公开 |
| 实现 | **私有仓库** | 后续会含实验数据、审计日志样本、可能的内部文档 |

**提交前自查是否有敏感内容**：

```bash
git diff --cached | grep -inE '(password|secret|token|api[_-]?key)\s*[=:]' | grep -v CHANGE_ME
```

`scripts/selftest.py` 也内置了密钥扫描，会拦住常见形态。

---

## 6. 常见问题

**Q: 相对链接 `../local-agent-learning-path/` 点不开？**
两个仓库不在同级目录。按 §4 的目录结构摆放。

**Q: `selftest.py` 报"配置对齐"失败？**
改了 `.env.example` 但没改 `packages/core/config.py` 的 `Settings`（或反之）。
这是有意设计的门禁，两边必须同时改。

**Q: 从 Windows 编辑 WSL 里的文件，中文乱码？**
用支持 UTF-8 的编辑器，不要用 PowerShell 管道改写。WSL 里的路径是
`\\wsl$\Ubuntu-22.04\home\zsw\projects\...`。

**Q: 提交历史里出现了 `.env`？**
立即 `git rm --cached .env`，**轮换所有相关密钥**，然后清理历史
（`git filter-repo`）。密钥一旦进了 git 历史就不能算作安全。
