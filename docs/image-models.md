# GPT Image 模型适配

模型 ID 与质量参数按 [OpenAI 图片接口文档](https://developers.openai.com/api/docs/guides/image-generation) 对齐（2026-11-10）。本项目使用 ChatGPT / Codex 账号接口，官方 API 文档不能证明该账号接口已开放某个模型。

| 请求模型 | 上游路径 | 质量 |
| --- | --- | --- |
| `gpt-image-2` | 原有官网会话路径，使用配置中的对话模型 | `auto` / `low` / `medium` / `high` |
| `codex-gpt-image-2` | Codex 图片工具，指定 `gpt-image-2` | 同上 |
| `gpt-image-2.5-sunburst` / `gpt-image-2.5-flare` | 官网 prepare / conversation 顶层 `model` 原样传递 | 上述质量及 `xhigh` / `max`，通过提示词引导 |
| `gpt-image-2.6-sunburst` / `gpt-image-2.6-flare` | 官网 prepare / conversation 顶层 `model` 原样传递 | 上述质量及 `xhigh` / `max`，通过提示词引导 |
| `codex-gpt-image-2.5-*` / `codex-gpt-image-2.6-*` | Codex `tools[].model`，去掉 `codex-` 前缀 | 上述质量及 `xhigh` / `max`，通过工具字段传递 |

`codex-` 前缀明确选择 Codex 链路，并接受 `plus-codex-`、`team-codex-`、`pro-codex-` 套餐前缀，例如 `team-codex-gpt-image-2.6-flare`。版本号简写 `gpt-image-2.5` / `gpt-image-2.6` 不会擅自选择 Sunburst 或 Flare。

标准 2.5 / 2.6 模型使用 `source_type=web` 或密码登录来源 `password` 的账号，不额外要求 Codex 套餐；实际权限与额度由官网决定。`codex-` 模型使用 `source_type=codex` 的 Plus / Team / Pro 账号。`GET /v1/models` 分别按这两类账号展示模型，不将模型目录当作权限探测。请求失败时不切换到另一条链路或旧模型。

Web prepare 明确返回 `status=ok, conduit_token=null` 时正常继续并省略 conduit 请求头；错误状态、缺少字段、非法 token 类型仍然报错。若 SSE 报告的 `model_slug` 与请求版本不一致，返回 `model_mismatch`。图片接口结果与结果流块中的 `_actual_model` 表示上游实际报告的模型，未上报时不伪造该字段。

## 请求示例

`POST /v1/images/generations`：

```json
{
  "model": "gpt-image-2.6-flare",
  "prompt": "一张极简产品海报",
  "quality": "xhigh",
  "complexity": "medium",
  "size": "1024x1024",
  "response_format": "b64_json"
}
```

`POST /v1/images/edits` 的 JSON / multipart 请求支持同样的模型、质量与复杂度字段，并按原接口传入图片。异步图片任务也会保留这些字段。`complexity` 可选值为 `low` / `medium` / `high`，当前仅对 2.6 开放。

Web 路径的 `size`、`quality`、`complexity` 通过提示词引导，实际尺寸、质量和规划强度由上游决定，不保证与官方 Image API 参数等效。Codex 路径通过工具字段传递，省略 `complexity` 时使用上游默认值。

`POST /v1/responses` 将对话模型和图片工具模型分开：

```json
{
  "model": "gpt-5.5",
  "input": "一张极简产品海报",
  "tools": [{
    "type": "image_generation",
    "model": "gpt-image-2.6-sunburst",
    "quality": "max",
    "complexity": "high"
  }]
}
```

该示例通过 Web 调用图片模型。将工具模型改为 `codex-gpt-image-2.6-sunburst` 可选择 Codex；Codex 的外层对话模型沿用项目配置。顶层 `model` 保留在兼容响应中。也支持直接以图片模型作为顶层 `model`。`POST /v1/chat/completions` 使用图片模型时，会传递顶层 `size`、`quality`、`complexity`。

## 当前边界与验证

- 维持原有 PNG 输出契约；SVG、动画 GIF、markup 编辑等新能力尚未适配。
- 图片工具结果在多个 SSE 事件重复出现时按调用 ID 去重。
- 优先返回图片工具上报的 `usage`。新模型未上报时省略 `usage`，避免使用旧模型公式伪造用量；旧模型保留原有估算逻辑。
- 回归测试检查模型 ID、账号路由、参数到达上游的请求体、JSON / multipart、Responses 工具选择、流式结果去重及旧模型兼容。不代表真实账号生图验收。

Web 选择位置的历史在线验证脱敏摘要保存在 [web-image-models.json](./evidence/web-image-models.json)：2026-10-28 的 2.5 Flare / Sunburst 生图返回匹配 `model_slug`；2026-11-05 的 2.6 Flare 动画请求也返回匹配模型和图片资产。公开摘要仅保留验证结果，不包含账号、凭据、原始提示词或来源文件路径。这些是历史账号验证，不能当作本次新验证。2.6 Sunburst 按相同协议接入，尚无在线成功证据。

Web / Codex 接口回归共 22 项，连同相关既有测试共 73 项通过，见 `test_image_model_versions.py` 和 `test_web_image_model_versions.py`。轮询测试显式启用 `image_settle_enabled` 和 `image_check_before_hit_enabled`，不修改本地配置文件。另有 `test_v1_images_edits_json.py` 的 4 项旧断言失败（文件名、缺图错误文案、远程 URL 支持），已用修改前 `HEAD` 的解析器复现相同失败。

前端通过独立 TypeScript 检查（`tsc --noEmit --incremental false`）及 Next.js 生产构建。此次未进行真实账号生图测试。

单独运行新增测试：

```bash
python -m unittest test.test_image_model_versions test.test_web_image_model_versions -q
```
