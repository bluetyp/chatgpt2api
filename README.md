# ChatGPT2API

将 ChatGPT Web / Codex 的图片生成与编辑能力封装为 OpenAI 兼容接口，并提供图片工作台、账号管理和 Docker 部署。

本仓库是基于 [basketikun/chatgpt2api](https://github.com/basketikun/chatgpt2api) 独立维护的衍生项目，保留原作者 `kunkun` 的版权声明与 MIT 许可证。它不是 OpenAI 官方产品，也不代表上游项目发布。

## 本分支的改动

- GPT Image 2.5 / 2.6 的 Sunburst、Flare 模型适配。
- 标准图片模型名走 ChatGPT Web；`codex-` 前缀走 Codex，分别选择对应来源的账号。
- Images、Chat Completions 和 Responses 的图片请求转换；Responses 正确读取 `tools[].model`。
- Web 空 conduit 成功响应、服务端实际模型核对，及 Codex 重复图片事件与用量处理。
- 独立仓库的配置模板、源码构建、可配置更新地址和回归测试入口。

上游历史保留在 [CHANGELOG.md](CHANGELOG.md)，本分支尚未发布的变更列在 `Unreleased`。

## 模型与验证范围

| 请求模型 | 账号来源 | 调用路径 |
| --- | --- | --- |
| `gpt-image-2` | 原有图片账号池 | Web 默认生图路径，沿用上游模型配置 |
| `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` | Web / 密码登录 | 官网顶层 `model` 指定图片模型 |
| `gpt-image-2.6-flare` / `gpt-image-2.6-sunburst` | Web / 密码登录 | 同上 |
| `codex-gpt-image-2`、`codex-gpt-image-2.5-*`、`codex-gpt-image-2.6-*` | Codex Plus / Team / Pro | 图片工具的 `model` 字段 |

完整模型名、套餐前缀和示例见[图片模型说明](docs/image-models.md)。`GET /v1/models` 表示本地可以路由的模型，不代表账号已经获得每个模型的权限。

历史 Web 验证覆盖 2.5 两个版本，以及 2.6 Flare 的动画请求；本仓库这次适配没有重新在线生图。2.6 Sunburst 和新 Codex 模型仍需真实账号验证。默认保持 PNG 输出契约，尚未适配 SVG、动画 GIF 和 markup 编辑。Web 的尺寸、质量、复杂度通过提示词引导，不保证与官方 Image API 的硬参数等效。

## 快速开始

需要 Docker 和 Docker Compose v2。克隆**当前仓库**后进入项目目录：

```bash
cp config.example.json config.json
cp .env.example .env
```

在 `.env` 中设置随机的 `CHATGPT2API_AUTH_KEY`。可以用下面的命令生成密钥，再自行写入 `.env`：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

从当前源码构建并启动：

```bash
docker compose up -d --build
```

- 管理面板：`http://127.0.0.1:3000`
- API：`http://127.0.0.1:3000/v1`
- 默认仅监听本机；远程部署时配置 HTTPS 反向代理及访问控制。
- `config.json`、`.env` 和 `data/` 是本机持久化数据，不应提交到 Git。
- 在账号页导入自己有权使用的账号。Web 与 Codex 来源、权限和额度分别由上游决定。

默认 Compose 使用本仓库源码构建，不拉取原作者的预构建镜像。高级部署、存储后端和升级步骤见[部署文档](docs/deployment.md)。

## API 示例

所有 `/v1` 请求都需要本服务的密钥；不要把上游账号 Token 当作客户端密钥。

```bash
curl http://127.0.0.1:3000/v1/images/generations \
  -H "Authorization: Bearer <本服务的 auth-key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-image-2.5-flare","prompt":"白色背景上的蓝色陶瓷杯","n":1}'
```

| 接口 | 用途 |
| --- | --- |
| `GET /v1/models` | 模型目录 |
| `POST /v1/images/generations` | 文生图 |
| `POST /v1/images/edits` | JSON / multipart 图片编辑 |
| `POST /v1/chat/completions` | 文本、搜索及图片兼容入口 |
| `POST /v1/responses` | 文本、搜索及图片工具兼容入口 |

这是一组兼容接口，不是 OpenAI 官方 API 的完整实现。更多请求示例见 [API 文档](docs/api.md)，其他继承功能见[功能状态](docs/feature-status.en.md)。

## 本地开发与验证

后端需要 Python 3.13+ 和 uv；前端需要 Node.js 22 与 Bun。先按快速开始准备本机配置和 `.env`。

```bash
uv sync --frozen
uv run --env-file .env main.py
```

另开终端启动前端：

```bash
cd web
bun install --frozen-lockfile
bun run dev
```

后端默认端口为 `8000`，前端开发端口为 `3000`。运行不需要真实账号或本地 API 服务的回归套件：

```bash
uv run scripts/run_unit_tests.py
```

前端检查：

```bash
cd web
bunx tsc --noEmit --incremental false
bun run build
```

`test/` 还包含需要真实服务和账号的手动集成脚本，不建议直接运行整个目录的自动发现。当前已知旧测试问题和在线验证边界见[模型说明](docs/image-models.md)。

## 使用与贡献

账号、Cookie、Token、代理凭据、生成内容和日志都应留在部署者自己的环境中。提交 Issue 或 PR 时使用脱敏日志与最小复现，不附上账号导出、HAR 或 `.env`。

本项目依赖非公开上游接口，接口变更、账号权限或限流都可能影响可用性。请遵守相关服务条款、法律和内容政策。软件代码的授权范围以 [MIT LICENSE](LICENSE) 为准；代码许可证不会授予第三方服务访问权限。

独立仓库的发布步骤、上游归属、历史检查和镜像配置见[发布准备说明](docs/publishing.md)。

## 来源与许可

感谢 [basketikun/chatgpt2api](https://github.com/basketikun/chatgpt2api) 原作者和贡献者。独立发布副本保留上游来源说明与版权许可，新增修改同样按 MIT 许可提供；旧提交历史不随该副本发布。原作者的赞助关系、社区入口和产品推荐不代表本分支的关系或背书。
