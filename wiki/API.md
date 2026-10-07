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
| GET / PATCH | `/api/config` | 配置概要 / 更新配置并热重载 |
| GET | `/api/config/full` | 配置全文（含 profile 结构） |
| PUT | `/api/config/secrets` | 设置密钥（永不回显） |
| GET | `/api/detection` | 聚合检测（环境 / 配置 / LLM·ASR·TTS 连通性） |
| GET | `/api/env` | 环境感知快照 |
| GET | `/api/tools` | 工具清单（@tool 注册中心的 OpenAI schema 数组） |
| POST | `/api/tools/call` | 单工具执行（是否询问由 `permissions` 策略决定） |
| POST | `/api/voice/utter` | **编排入口**：文本 → SSE 事件流（唯一 agent 路径，`mode`: chat/task） |
| POST | `/api/voice/answer` | 投递澄清/确认问题的回答（可带 qid 配对，解除 ask() 阻塞） |
| POST | `/api/voice/resume` | SSE 断线后续播（`server.resume_grace_s` 宽限期内任务继续） |
| POST | `/api/voice/call/start` · `/api/voice/call/stop` | 通话模式开 / 关（建立漏斗会话；无段落 300s 自动过期，期间与唤醒互斥） |
| POST | `/api/voice/call/segment` | 通话段落进三级漏斗（L0 规则 → L1 本地转写 → L2 云端精判）；请求体 `audio_base64` + `tab_focused` / `in_open_window`，响应 `hit` / `text` / `stage` / `reason`，`hit` 才由前端送 `/voice/utter` 编排 |
| POST | `/api/voice/wake/check` | 本地 KWS 快检：只回答「有没有唤醒词」（毫秒级、零云端调用） |
| POST | `/api/voice/wake` | 唤醒检测：转写 + 判定 + 切指令（mode=cloud 旁路本地闸门） |
| POST | `/api/voice/transcribe` | ASR 转写（JSON 体 audio_base64，16kHz mono WAV） |
| GET | `/api/voice/upload-stats` | 云端上传成本统计：`audio-upload via=wake/transcribe/call-segment` 三前缀计数 + 近 7 日趋势（**只回计数与日期**，绝不回放转写文本）；数据源 `data/audit.log`，统计页成本仪表用 |
| POST | `/api/tts` | 文本转语音（返回音频字节） |
| GET | `/api/memory` · DELETE `/api/memory/{topic}` | 长期记忆浏览/删除 |
| GET / POST | `/api/history` · GET/DELETE `/api/history/{conv_id}` | 会话历史列表 / 详情 / 删除 |
| GET | `/api/library` · GET/DELETE `/api/library/{task_id}` | 任务知识库浏览 / 详情 / 删除 |
| GET / POST | `/api/sessions` · PATCH/DELETE `/api/sessions/{sid}` | 会话列表 / 新建 / 改名 / 归档删除 |
| POST | `/api/sessions/{sid}/clear` · `/api/sessions/{sid}/fork` | 清空会话 / 分叉编辑 |
| GET / POST | `/api/schedules` · DELETE `/api/schedules/{sid}` | 定时任务列表/注册/取消 |
| GET | `/api/providers` · POST `/api/providers/fetch-models` | 厂商目录 / 拉取可用模型列表 |
| POST | `/api/task/{session_id}/stop` | 停止该会话整个任务 |

完整 schema 见 `GET /openapi.json`（前端 `web/src/api/generated.ts` 由其生成，
CI 校验两者同步）。

## SSE 事件（`POST /api/voice/utter`）

请求体：`{ text, mode?, messages? }`（`mode`: `chat`/`task`，缺省 chat；
`messages` 为多轮历史种子，含当前用户消息）。

所有事件携带公共字段 `turn_id`（所属回合：一次用户话语 → 一次编排运行 → `done`）；
事件形状**只增不改**——新增可选字段默认不下发，旧前端零感知。

| 事件 | 含义 |
|------|------|
| `task_state` | 编排状态流转（`understanding` / `notify` / `done`，done 含 status/summary/steps） |
| `content_delta` / `reasoning_delta` | 文本 / 思考增量（任务答复也流式返回） |
| `tool_start` / `tool_end` | 工具开始 / 结束（tool_end 含 output 与 status） |
| `usage` | token 用量增量 |
| `question` | 需要操作者回答（澄清/确认，带 qid），回答走 `/api/voice/answer` |
| `answer` | 操作员作答入块（qid/text/choice/source，语音可审计） |
| `block` | 离散消息块直通（image/file/ext:* 等即插即用） |
| `done` | 本轮完成（含 session_id） |
| `error` | 出错（含 message） |

**网络健壮性**：前端对「未收到任何事件」的网络错误自动重试一次；HTTP/业务错误与流中段不重试。
