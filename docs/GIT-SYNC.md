# Git 同步说明

> 两个仓库**独立管理、独立提交**。指南是"教材"，本项目是"作业"。

---

## 1. 两个仓库的关系

```
/home/zsw/work/agent_development/
├── Agent-development-doc/      仓库 A —— 指南（教材）
│   └── 相对稳定，改动少，主要在修订时提交
└── Agent-development-code/     仓库 B —— 实现（作业）
    └── 高频提交，按里程碑打 tag
```

**为什么分开**：

1. 指南里有指向 `../Agent-development-doc/` 的相对链接，同目录结构下才能点开
2. 指南是别人（或你自己）写的规范，实现是你写的代码 —— 版本演进节奏完全不同
3. 如果合并成一个仓库，M1 的一个小改动会污染指南的提交历史

**代价**：新机器 clone 时**两个都要 clone**，且必须放在同级目录。
本文件的 §4 给出精确命令。

---

## 2. 仓库 A：指南

```bash
cd /home/zsw/work/agent_development
git clone <指南远端> Agent-development-doc
cd Agent-development-doc

# 提交前跑指南自带的三个检查
python3 eval/validate_dataset.py --all --mode draft
python3 -m unittest discover -s eval -p 'test_*.py' -v
python3 scripts/check_docs.py
```

**易踩的坑**：

- **编辑一律在 Ubuntu 内完成**。不要用 Windows 侧工具经 `/mnt/c`、`/mnt/d`
  改写这些 Markdown —— 编码转换会把中文变成 mojibake
  （历史上发生过一次）。用 Ubuntu 内的编辑器，或 Python 显式 `encoding="utf-8"`。
- `.gitignore` 已排除 `eval/results/`；`data/` 与 `.venv/` 同理。

---

## 3. 仓库 B：实现

```bash
cd /home/zsw/work/agent_development/Agent-development-code

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
docs: 记录为什么 Ollama 也放在 Ubuntu 内
```

---

## 4. 新机器部署（完整流程，全部在 Ubuntu 内）

```bash
# 1. 目录结构必须同级，否则相对链接会断
mkdir -p /home/zsw/work/agent_development && cd /home/zsw/work/agent_development

# 2. 两个都 clone
git clone <指南远端>  Agent-development-doc
git clone <实现远端>  Agent-development-code

# 3. 环境（详见指南 01-ENVIRONMENT.md）
sudo apt update && sudo apt install -y docker-compose-plugin
cd /home/zsw/work/agent_development/Agent-development-code
uv venv --python 3.12 .venv && source .venv/bin/activate
uv sync --extra m1 --extra dev
cp .env.example .env          # Ollama 在本机回环，默认值即可用

# 4. 确认 Ollama 服务（应已在 Ubuntu 内运行）
systemctl status ollama --no-pager
curl -s http://127.0.0.1:11434/api/version
ollama pull qwen3.5:4b        # Phase 0 唯一必需模型

# 5. 验证
python3 scripts/selftest.py
uv run pytest -q
```

**Windows 侧不需要任何配置**。前端就绪后（M6），Windows 只用浏览器访问：

```text
http://<Ubuntu 地址>:<port>        # 取地址：hostname -I | awk '{print $1}'
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

**Q: 相对链接 `../Agent-development-doc/` 点不开？**
两个仓库不在同级目录。按 §4 的目录结构摆放。

**Q: `selftest.py` 报"配置对齐"失败？**
改了 `.env.example` 但没改 `packages/core/config.py` 的 `Settings`（或反之）。
这是有意设计的门禁，两边必须同时改。

**Q: 从 Windows 侧改 Ubuntu 里的文件，中文乱码？**
不要这样做 —— 编辑一律在 Ubuntu 内完成（用 Ubuntu 内的编辑器，或 Python 显式
`encoding="utf-8"`）。本项目的实现步骤里没有 Windows 侧编辑这一环。

**Q: `OLLAMA_BASE_URL` 连不上？**
Ollama 现在是 Ubuntu 内的 systemd 服务，走回环。依次检查：

```bash
systemctl status ollama --no-pager     # 服务是否运行
ss -ltnp | grep 11434                  # 是否监听 127.0.0.1:11434
curl -s http://127.0.0.1:11434/api/version
```

不要再把它改成宿主 IP 或对外地址 —— 跨系统访问 Ollama 的前提已不存在（指南 §5）。

**Q: 提交历史里出现了 `.env`？**
立即 `git rm --cached .env`，**轮换所有相关密钥**，然后清理历史
（`git filter-repo`）。密钥一旦进了 git 历史就不能算作安全。
