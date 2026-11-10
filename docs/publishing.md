# 独立仓库发布准备

项目名称保持 **ChatGPT2API**，发布到新的 GitHub 仓库。本分支基于 `basketikun/chatgpt2api` 的提交 `92dd80e` 开始整理。为避免继承旧记录中的路径、截图与账号资料，独立发布副本仅包含审核后的文件，不携带旧 Git 历史；原开发仓库保留不变。新建仓库不等于从零原创，版权和来源说明仍需保留。

## 来源与许可证

- 保留根目录 `LICENSE` 中的 `Copyright (c) 2026 kunkun` 及完整 MIT 条文。
- README 显式声明衍生来源和独立维护关系；移除原作者的赞助商广告、外部截图、社区推广、贡献者图片与 Star History。
- MIT 明确允许使用、修改、分发和销售，并要求保留版权及许可声明。因此本分支不再重复原 README 的“禁止商用”说法。参见 [MIT 正文](https://opensource.org/license/mit)。
- 第三方服务访问权、模型权限、素材版权及相关服务条款不由代码许可证授予。
- 以后新增代码或素材若来自其他项目，应分别检查许可证，不能因为本仓库使用 MIT 就自动视为全部 MIT。

## 已做的本地清理

- 主 README 缩减为项目定位、本分支差异、验证范围、快速开始、API 示例、开发与贡献说明；详细接口移到 `docs/api.md`。
- `config.json` 停止 Git 跟踪，保留本机文件；仓库提供空密钥的 `config.example.json`。
- Docker 镜像只复制配置模板，并包含 `LICENSE`；构建上下文排除账号数据、环境文件、备份、抓包和本地分析材料。
- 默认 Compose 从当前源码构建，避免下载仍未包含本分支改动的上游镜像；默认绑定 `127.0.0.1`。
- 前端源码链接和版本检查地址通过构建变量指定，未配置时不向上游查询更新。
- 镜像发布工作流自动使用当前 GitHub 仓库名生成 GHCR 地址；不会发布到原作者命名空间。
- 提供 `scripts/run_unit_tests.py` 和 CI 工作流，区分隔离回归与真实账号集成脚本。
- 镜像发布先运行回归及前端检查，通过后才构建并推送；容器启动使用已安装依赖，不在启动时重新同步开发依赖。

`git rm --cached config.json` 只影响将来的提交，不会删除旧提交中的内容。

## 当前扫描范围

2026-11-10 对本地所有 Git 引用可达的 **333 个提交 / 1,247 个 blob**，以及当时 **213 个候选工作区文件**进行了规则扫描，检查 JWT、GitHub Token、常见 API Key、AWS Access Key、私钥标记和配置中的非占位凭据，未发现高置信度命中。扫描没有把匹配值输出到报告。

这不是完整安全审计：短密码、非标准凭据、图片中的信息、私人域名、压缩包或外部链接需要人工复查。发布前建议另用 Gitleaks / GitHub Secret Scanning 检查最终提交。如果确有真实凭据进入历史，先撤销或轮换，再决定是否清理历史；不要仅删除当前文件。参见 [GitHub 敏感数据处理说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。

原始 HAR、账号导出、本地分析报告、`data/`、`.env` 和真实配置均不应发布。`docs/evidence/` 仅保留脱敏摘要；其中历史验证不代表新仓库已经重新完成在线测试。

再次隐私复核已去掉证据摘要中的外部项目相对路径、其他项目描述，以及脚本中的固定桌面文件路径。上游历史包含旧截图及路径，因此本次采用无历史的发布副本，不直接推送原开发分支。容器内部的 `/app`、上游沙箱协议的 `/mnt/data` 等功能路径不是部署者的本机目录，不应为脱敏而破坏协议。

发布副本经过 Gitleaks v8.30.1 离线扫描。两处公开 Auth0 SDK 元数据被通用 API Key 规则误报；解码内容仅为 SDK 名称与版本，已在 `.gitleaks.toml` 中按文件及完整固定值添加精确例外，不豁免真实凭据。CI 同样扫描文件与历史。Docker 构建上下文另行实测，嵌套 Python 字节码会携带构建机器路径，已通过递归规则排除。

## 发布前验证

2026-11-10 本地准备结果：

| 检查 | 结果 |
| --- | --- |
| 不含本机配置及账号数据的发布副本 | 73 项回归通过 |
| 前端独立 TypeScript 检查 / 生产构建 | 通过 |
| 三份 Compose 配置解析 | 通过 |
| 工作流 YAML 解析、文档链接及 Git diff 空白检查 | 通过；未在 GitHub 执行工作流 |
| 完整 Docker 镜像 | 未完成：初次 Debian HTTP 源返回 502，改用官方 HTTPS 后通过；npm 出现连接重置，加入有限超时后通过，随后 Bun 依赖安装超过五分钟无进展，已停止。发布镜像前需要重新构建验收 |
| 真正账号生图与 arm64 镜像 | 本轮未验证 |

```bash
uv sync --frozen
uv run scripts/run_unit_tests.py
cd web
bun install --frozen-lockfile
bunx tsc --noEmit --incremental false
bun run build
```

再用新 checkout 或不包含本地配置的工作副本检查：

```bash
cp config.example.json config.json
cp .env.example .env
# 设置 .env 的 CHATGPT2API_AUTH_KEY 后执行
docker compose config --quiet
docker compose build
```

不要用 `unittest discover` 的全目录结果代替隔离套件；现有目录混有在线测试，另有旧编辑测试断言需要单独更新，详见模型说明。

## 仓库地址与更新入口

仓库地址确定后，在本地构建用的 `.env` 中配置：

```dotenv
NEXT_PUBLIC_REPOSITORY_URL=https://github.com/OWNER/chatgpt2api
NEXT_PUBLIC_RELEASE_BASE_URL=https://raw.githubusercontent.com/OWNER/chatgpt2api/main
```

这两个变量是公开 URL，不能填写 Token。它们在前端构建时固化，修改后需要重新构建镜像。GitHub 镜像工作流会自动设置为当前仓库及默认分支。

Compose 从根目录 `.env` 读取这些构建参数。直接在 `web/` 运行前端构建时，应通过终端环境变量或不提交的 `web/.env.local` 提供它们。

先确定本分支首个版本，再同步 `VERSION`、`CHANGELOG.md`、必要的包元数据及 tag。目前 `VERSION` 沿用上游 1.8.0；不要把上游旧 tag 当作本分支已经发布的版本。

## 推送到新仓库

在 GitHub 创建空仓库，名称使用 `chatgpt2api`，暂不自动生成 README、许可证或 `.gitignore`，以避免首次推送产生无关根提交。初始 GitHub 仓库也可以设为 private，在完成最终检查后再公开。

只在已审核、无旧历史的发布副本中操作。副本默认分支为 `main`，没有远程地址、提交、旧 tag 或旧对象，文件已暂存。原开发仓库仍用于继续开发，不作为此次直接推送源。

Git 提交会公开作者姓名及邮箱。先确认本机 Git 身份；如需隐藏个人邮箱，在 GitHub 邮箱设置中取得自己的 noreply 地址，并为发布副本单独配置公开身份。下列占位值必须替换，不能原样使用：

```bash
git config --local user.name "你的公开署名"
git config --local user.email "你的 GitHub noreply 地址"
git remote add origin https://github.com/OWNER/chatgpt2api.git
git remote -v
git status --short
git diff --cached --stat
```

检查 `git diff --cached` 后创建首次提交，再推送新仓库：

```bash
git commit -m "Prepare independently maintained ChatGPT2API"
git push -u origin main
```

首次发布不需要 `--mirror`、`--all`、`--tags` 或强制推送。这些操作会额外发布引用或改变远程历史。

新仓库配置分支保护、CI 状态检查、依赖告警与 Secret Scanning；确认包权限及 GHCR 可见性后再创建本分支的版本 tag。工作流会在 `v*` tag 或手动触发时推送镜像，因此不要用未审核 tag 试运行正式发布。

建议仓库描述：`Independently maintained ChatGPT Web and Codex image API compatibility service.`
