# API 参考

统一前缀 `/api`，REST + SSE（无 WebSocket）。SSE 用 `fetch` + `ReadableStream` 解析。

## 认证

- 默认只绑定 `127.0.0.1`，无认证。
- `server.host` 改为非 localhost 时必须设置 `server.api_token`，所有 `/api/*` 请求需携带请求头：
  ```
  X-API-Token: <token>
  ```
- 静态资源（前端页面/模型）不校验。

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ping` | 健康检查 |
| GET | `/api/config` | 配置概要（LLM/ASR/TTS profile、唤醒词、VAD） |
| GET | `/api/tools` | 工具清单（@tool 注册中心的 OpenAI schema 数组） |
| POST | `/api/voice/utter` | **编排入口**：文本 → SSE 事件流（唯一 agent 路径） |
| POST | `/api/voice/answer` | 投递澄清/确认问题的回答（解除 ask() 阻塞） |
| POST | `/api/task/{session_id}/stop` | 停止该会话整个任务 |
| POST | `/api/tools/call` | 单工具执行（前端「重试失败工具」用） |
| POST | `/api/voice/transcribe` | ASR 转写（JSON 体 audio_base64，16kHz mono WAV） |
| POST | `/api/tts` | 文本转语音（返回音频字节） |
| GET | `/api/env` | 环境感知快照 |
| GET | `/api/memory` · DELETE `/api/memory/{topic}` | 长期记忆浏览/删除 |
| GET/POST | `/api/schedules` · DELETE `/api/schedules/{sid}` | 定时任务列表/注册/取消 |

## SSE 事件（`POST /api/voice/utter`）

请求体：`{ text, messages? }`（`messages` 为多轮历史种子，含当前用户消息）。

| 事件 | 含义 |
|------|------|
| `task_state` | 编排状态流转（`understanding` / `notify` / `done`，done 含 status/summary/steps） |
| `content_delta` / `reasoning_delta` | 文本 / 思考增量（任务答复也流式返回） |
| `tool_start` / `tool_end` | 工具开始 / 结束（tool_end 含 output 与 status） |
| `usage` | token 用量增量 |
| `question` | 需要操作者回答（澄清/确认），回答走 `/api/voice/answer` |
| `done` | 本轮完成（含 session_id） |
| `error` | 出错（含 message） |

**网络健壮性**：前端对「未收到任何事件」的网络错误自动重试一次；HTTP/业务错误与流中段不重试。
