# 无限逻辑·语音助手 — 重构设计文档

日期：2026-08-08
状态：已确认（用户审批通过）

## 背景

原项目为"AI  消息Agent"（ 网络OA  语音助手+ 悬浮球语音助手）。本次重构：
- 删除全部**消息**与**网络**相关代码
- 只保留**语音链路**（唤醒词 → ASR → LLM → TTS）
- 配置统一为**外网 OpenAI 兼容**格式
- 产品名改为**无限逻辑·语音助手**，物理目录不变
- **git 重新初始化**（删 `.git` 重新 init 提交）

## 已确认需求

| 项 | 决定 |
|---|---|
| 助手定位 | 语音对话 + 通用工具扩展框架（本轮无具体工具，仅留接口） |
| LLM | DeepSeek（OpenAI 兼容），ASR/TTS 统一 OpenAI 兼容格式 |
| 唤醒词 / 助手名 | "小逻小逻" / "小逻"（保留离线 Vosk 引擎，关键词可配置） |
| 前端形态 | 极简单页 + 悬浮球（全屏深色背景 + 居中标题 + 唤醒词提示） |
| 目录改名 | 只改产品名，物理目录 `InfiniteLogicAssistant` 不变 |
| git | 删除 `.git` 重新初始化 |

## 文件增删清单

### 删除（Python 模块，8 个）
- `core/mail_api.py`
- `core/mail_sender.py`
- `core/mail_browser.py`
- `core/monitor.py`
- `core/notify.py`
- `core/models.py`
- `core/user_id.py`
- `core/原单位.py`

### 修改（Python）
- `main.py`：只留 `serve` / `test` 命令；删 `user-info`、`monitor` 命令与凭据校验。
- `server.py`：只留 `ping` / `config` / `ai/chat` / `voice/transcribe` 4 个端点；删消息与 AI 高级端点；**去掉 CORS 头**（前后端同源）。
- `core/config.py`：删 auth/mail/notify/monitor 配置段；llm/asr/tts 只留 openai 兼容 profile（deepseek 默认 + openai/通义示例）；删  加密相关键与  原单位相关默认值。
- `core/llm/__init__.py`：删  qwen 模型provider 及全部  原单位代码；删 summarize/reply/polish/classify/parse_voice_command 消息向高层函数；只留 `chat` / `_call` / `available`。
- `core/voice/__init__.py`：删  原单位ASR/TTS provider 分支，只留 openai 分支。

### 删除（前端组件，6 个）
- `web/src/components/AppHeader.vue`
- `web/src/components/Sidebar.vue`
- `web/src/components/MailList.vue`
- `web/src/components/MailDetail.vue`
- `web/src/components/ComposeForm.vue`
- `web/src/components/SettingsPanel.vue`

### 修改（前端）
- `web/src/App.vue`：重写为极简单页（全屏深色背景 + 居中标题"无限逻辑·语音助手" + 唤醒词提示 + FloatingAssistant）。
- `web/src/components/FloatingAssistant.vue`：删 `open-compose` emit（行 155/406）与消息工具图标/文案映射（send_email/check_inbox/get_email_detail/open_compose，行 265-279）；保留悬浮球/聊天面板/状态 UI。
- `web/src/composables/useAssistant.ts`：SYSTEM_PROMPT 改为通用助手"小逻"；TOOLS 只保留 `chat` 工具 + 注释标注扩展点；`handleAction` 删 4 个消息工具分支，保留工具调用框架；删 `setRefreshEmailsHandler`/`onRefreshEmails`（行 100-110/662）。
- `web/src/api.ts` / `web/src/types.ts`：重写，只留 `ping` / `config` / `transcribe` 及对应类型（ConfigResponse/TextResponse/WakeWordConfig/VadConfig）；删全部消息与 AI 高级接口及 Email 类型。
- `web/src/composables/useApi.ts`：删 useEmails/useCompose/useAi，保留 useConfig（读 `/api/config`）。
- `web/src/styles/app.css`：清理消息样式（mail-list 等），保留/调整为语音助手单页样式。
- `web/index.html`：标题改为"无限逻辑·语音助手"。

### 其他
- `data/`：删 `read_state.json`、`downloads/`、`monitor_state.json`、`monitor.lock`、旧 `agent.log`。
- `scripts/libs/`：删 gmssl / pycryptodomex 离线 wheel（加密/SM3 网络专用）；**保留** win32_setctime（loguru 的 Windows 依赖）、colorama/certifi/charset_normalizer/idna/urllib3（requests 依赖）、pyyaml。
- `requirements.txt`：删 `gmssl`、`pycryptodomex`。
- `README.md` / `start.bat` / `install_deps.bat` / `package_deploy.bat` / `config.yaml` / `config.yaml.example`：重写为语音助手 + 外网配置。
- git：删 `.git` → `git init` → 初始提交（含设计文档）。

## 后端 API（只留 4 个）

```
GET  /api/ping          # 存活检查
GET  /api/config        # llm/asr/tts 可用状态 + wake_word + vad
POST /api/ai/chat       # LLM 对话（悬浮球使用）
POST /api/voice/transcribe
```

静态托管 `web/dist` 保留不变。删除 CORS 头（前端与 API 同源托管）。

## 语音数据流（保留已验证链路）

唤醒"小逻小逻" → MediaRecorder 录音 → VAD 静音自动停止 → webm→16kHz mono WAV base64 → `POST /api/voice/transcribe`（OpenAI 兼容 ASR）→ 转文字 → `POST /api/ai/chat`（DeepSeek）→ 返回 JSON action（本轮仅 `chat`，预留工具扩展）→ SpeechSynthesis 播报。

## 配置设计（外网统一）

```yaml
llm:
  active: deepseek
  profiles:
    deepseek: { provider: openai, endpoint: https://api.deepseek.com, api_key: ${LLM_API_KEY}, model: deepseek-chat, chat_path: /v1/chat/completions, max_tokens: 4096, temperature: 0.7, timeout: 60 }
    openai:   { provider: openai, endpoint: https://api.openai.com/v1, api_key: ${OPENAI_API_KEY}, model: gpt-4o-mini }
    qwen:     { provider: openai, endpoint: https://dashscope.aliyuncs.com/compatible-mode/v1, api_key: ${QWEN_API_KEY}, model: qwen-plus }
voice:
  wake_word:
    enabled: true
    keyword: "小逻小逻"
    sensitivity: 0.5
    model_path: "models/vosk-model-small-cn-0.22"
  vad:
    silence_threshold: 0.02
    silence_duration_ms: 1500
    max_duration_ms: 10000
  asr:
    active: openai
    profiles:
      openai: { provider: openai, endpoint: "", api_key: ${ASR_API_KEY}, model: "" }
  tts:
    enabled: false
    profiles:
      openai: { provider: openai, endpoint: "", api_key: ${TTS_API_KEY}, model: tts-1, voice: alloy }
server:
  host: 127.0.0.1
  port: 8520
  open_browser: true
```

说明：
- 多 profile 机制保留，切换服务商只改 `active`。
- 所有网络字段（加密、serving_id、/serving/models/ 前缀、appId 等）全部移除。
- `${ENV_VAR}` 环境变量插值机制保留。
- `llm.features` 配置段删除（消息向 AI 功能已移除，无可用开关）。
- ASR / TTS 的 endpoint 与 model 故意留空：DeepSeek 不提供 ASR/TTS，由用户自填 OpenAI 兼容服务（如通义/硅基流动/MiMo 等）；填之前对应 `is_*_configured()` 返回 False，功能自动禁用。

## 错误处理与验证

- LLM 响应沿用现有 JSON 提取 + 纯文本兜底逻辑。
- 保留 `python main.py test` 连通性测试（LLM/ASR），`start.bat` 启动前调用。
- 验收标准：
  1. `npm run build`（vue-tsc 类型检查）通过
  2. `python main.py serve` 启动，冒烟测试 4 个端点
  3. 悬浮球页面打开，唤醒词/录音/对话/播报链路可用
  4. 全库无 `原单位` / `加密` / `mail` / `网络` 残留引用（git grep 校验）
