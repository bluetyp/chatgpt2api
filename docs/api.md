# API 兼容接口

以下示例假定本服务部署在 `http://127.0.0.1:3000`。所有 `/v1` 请求需要 `Authorization: Bearer <本服务的 auth-key>`。

## 模型目录

```bash
curl http://127.0.0.1:3000/v1/models \
  -H "Authorization: Bearer <auth-key>"
```

目录合并上游文本模型和本地账号可路由的图片模型。完整的 Web / Codex 区别及验证范围见[图片模型说明](image-models.md)。

## 图片生成

```bash
curl http://127.0.0.1:3000/v1/images/generations \
  -H "Authorization: Bearer <auth-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2.6-flare",
    "prompt": "白色背景上的蓝色陶瓷杯",
    "n": 1,
    "quality": "high",
    "response_format": "b64_json"
  }'
```

| 字段 | 说明 |
| --- | --- |
| `model` | 默认 `gpt-image-2`；标准 2.5 / 2.6 名称走 Web，`codex-` 前缀走 Codex |
| `prompt` | 必填 |
| `n` | 1–4 |
| `size` | 可选尺寸，Web 路径是提示词目标 |
| `quality` | `auto` / `low` / `medium` / `high`；2.5 / 2.6 另支持 `xhigh` / `max` |
| `complexity` | 2.6 可选：`low` / `medium` / `high`；Web 是提示词目标 |
| `response_format` | `b64_json` 或 `url` |
| `stream` | 返回项目的图片进度及结果事件，不是官方逐步图片事件的完整实现 |

Web 响应若报告实际模型，会通过 `_actual_model` 返回；与指定版本冲突时返回 `model_mismatch`。新模型没有上报用量时省略 `usage`。

## 图片编辑

```bash
curl http://127.0.0.1:3000/v1/images/edits \
  -H "Authorization: Bearer <auth-key>" \
  -F "model=gpt-image-2.5-flare" \
  -F "prompt=把杯子改成红色" \
  -F "image=@./input.png"
```

也支持 JSON 图片 URL、data URL 或 base64；例如：

```json
{
  "model": "gpt-image-2.5-flare",
  "prompt": "把杯子改成红色",
  "images": [{"image_url": "https://example.com/input.png"}]
}
```

表单可以重复 `image` / `image[]` 或 `image_url` 字段传入多张参考图。`file_id` 引用不支持。模型和质量字段与图片生成一致。

## Chat Completions 图片请求

```json
{
  "model": "gpt-image-2.5-flare",
  "messages": [{"role": "user", "content": "生成一张蓝色陶瓷杯的图片"}],
  "stream": false
}
```

发送到 `POST /v1/chat/completions`。图片结果以助手内容中的图片 Markdown 返回。文本与搜索兼容能力见[功能状态](feature-status.en.md)。

## Responses 图片工具

```json
{
  "model": "gpt-5.5",
  "input": "生成一张蓝色陶瓷杯的图片",
  "tools": [{"type": "image_generation", "model": "gpt-image-2.5-flare"}]
}
```

发送到 `POST /v1/responses`。图片模型由 `tools[].model` 选择；使用 `codex-gpt-image-2.5-flare` 可选择 Codex 路径。顶层模型会在兼容响应中回显，图片请求不等于对该顶层模型执行通用工具编排。

目前不承诺完整的官方 Responses 状态管理、任意工具执行、所有多模态输入或输出格式兼容。
