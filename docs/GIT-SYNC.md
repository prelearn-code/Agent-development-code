# 指定仓库与远端同步

本次改动仅在D盘代码仓库，并按用户授权推送远端。**用户WSL仓库由用户自行同步；助手不直接进入它操作。**D盘与Ubuntu可以指向同一remote，但工作区、依赖与未提交改动独立，不复制虚拟环境或私钥。

## 1. 四仓库同级与版本

```text
/home/zsw/work/agent_development/
├── Agent-development-doc/
├── Agent-development-code/
├── openssl/
└── GmSSL/
```

文档/代码独立Git与commit，密码源码亦独立；实际版本/tag按已验证路线固定。D盘本次只改代码，不同步用户WSL工作区或其未跟踪uv.lock。

## 2. 用户在Ubuntu自行更新

先核对路径/分支与自己的改动；工作区干净时：

```bash
cd /home/zsw/work/agent_development/Agent-development-code
git status --short --branch
git fetch origin
git pull --ff-only
python3 scripts/selftest.py --stage V1 --strict
python3 -m packages.app status
```

如有自己的代码、锁文件或配置，先决定提交/保留并合并，不使用覆盖式reset/clean。本次没有加入uv.lock，用户已有锁文件不被改写；依赖分组扩充后在自己的环境确认lock与所选extras。runner尚未写时run命令应报未实现。

## 3. 本地修改与提交门禁

仅操作人指定仓库。检查工作区、取远端，干净落后分支用快进；禁止覆盖未知改动。提交前按AGENTS做当前V自检、pytest和相关检查，固定原正确断言和gold。

提交真实源代码、配置样例和可定位文档；不提交.env、数据/产物/材料、依赖目录、检查缓存。标签只在本人验收后创建，V交付与M专项标签分别按03判断；红线Loop提交由本人完成，不替本人写ADR。

## 4. 环境约定

真实开发/模型/密码库/DB/API/Web在Ubuntu ext4，Ollama在Ubuntu回环，Windows仅访问页面。当前D盘入口测试是跨平台骨架验证，不说明WSL业务已验收。地址/依赖问题按01环境与实际配置检查，不让密码服务裸露公网。
