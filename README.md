# 无限逻辑·语音助手

基于浏览器 Vosk 离线唤醒词的语音对话助手。纯浏览器 + 轻量 Python 后端，
OpenAI 兼容接口，支持离线/在线任意部署。

## 功能

| 模块 | 功能 |
|------|------|
| 悬浮球助手 | 右下角可拖拽悬浮球，语音对话 + 聊天气泡面板 + 迷你播放条 |
| 语音唤醒 | 离线 Vosk WASM 唤醒词"小逻小逻"（含同音字变体匹配），纯浏览器运行 |
| 语音输入 | ASR（OpenAI 兼容）转文字，自动填入 |
| AI 对话 | LLM（OpenAI 兼容：DeepSeek / OpenAI / 通义…）多 profile 切换，ReAct 工具调用（时间/计算/搜索/天气） |
| 语音播报 | 浏览器 SpeechSynthesis API 播报助手回复 |

## 快速开始

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt
# 离线安装: 双击 install_deps.bat（使用 scripts/libs/ 下的离线 wheel）

# 2. 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入 LLM / ASR endpoint 和凭据（${ENV_VAR} 支持环境变量）

# 3. 启动（一键：前端 + 后端）
python main.py serve                  # 浏览器自动打开 http://127.0.0.1:8520
```

`python main.py serve` 同时提供前端页面（`web/dist`）与 `/api/*` 接口，打开一个端口即可使用。

**一键启动脚本**（Windows，含 LLM/ASR 连通性测试）：

```bat
start.bat
```

> 若 `web/dist` 未构建，前端需另行构建：

```bash
cd web
npm install
npm run build        # 产物在 web/dist/，serve 即托管该目录
```

开发模式（前端热更新）：

```bash
cd web
npm install && npm run dev     # 访问 http://127.0.0.1:5173 （vite 代理 /api → 8520）
```

## 语音助手使用

启动前端后，页面右下角出现可拖拽的悬浮球：

- **双击悬浮球** 或点击面板内"👂 开启"启动语音唤醒
- 说 **"小逻小逻"**（含同音字变体）激活录音
- 录音 **VAD 静音检测自动停止**（默认静音 1.5s），最长 10s 上限
- 录音经 ASR 转文字 → LLM 对话 → 结果用浏览器 TTS 语音播报

唤醒词、静音阈值等可在 `config.yaml` 的 `voice.wake_word` / `voice.vad` 中调整。

## API 端点

```
GET  /api/ping
GET  /api/config
POST /api/ai/chat          # SSE 流式聊天（ReAct + 工具）
POST /api/voice/transcribe # JSON 体传 audio_base64（16kHz mono WAV）
POST /api/tools/call       # 单工具执行（前端"重试失败工具"按钮用）
```

`POST /api/ai/chat` 返回 `text/event-stream`，每行 `data: {json}\n\n`，事件类型：

| 事件 | 含义 |
|------|------|
| `content_delta` / `reasoning_delta` | 文本 / 思考增量 |
| `tool_start` / `tool_end` | 工具开始 / 结束（`tool_end` 含 `output` 结果与 `status`） |
| `done` | 本轮完成 |
| `error` | 出错（含 `message`） |

## 命令

```
start.bat                   一键启动（Windows，含 LLM/ASR 连通性测试）
python main.py serve        启动 Web 服务（前端 + 后端 API）
python main.py test         测试 LLM / ASR 连通性
```

## 测试

```
python -m pytest tests/ -q   # 后端单元测试（工具 / ReAct / SSE 解析 / API）
cd web && npm run build      # 前端类型检查（vue-tsc）+ 生产构建
```

## 配置

`config.yaml.example` 为完整模板，支持 `${ENV_VAR}` 环境变量插值。核心段：

- `llm`：OpenAI 兼容 LLM，多 profile（deepseek / openai / qwen），改 `active` 切换。
- `voice.asr`：OpenAI 兼容 ASR（endpoint/model 自填，DeepSeek 无 ASR 服务）。
- `voice.tts`：可选后端 TTS；默认用浏览器 SpeechSynthesis 播报。
- `voice.wake_word` / `voice.vad`：唤醒词与静音检测参数。

## 目录结构

```
无限逻辑-语音助手/
├── main.py                   入口 (serve / test)
├── server.py                 HTTP 服务（/api/* + 托管 web/dist 前端）
├── start.bat / install_deps.bat / package_deploy.bat
├── config.yaml.example       配置模板
├── requirements.txt          Python 依赖
├── core/
│   ├── config.py             配置加载（YAML + ${ENV} 插值 + 多 profile）
│   ├── logger.py             loguru 日志（控制台 + data/agent.log）
│   ├── agent.py              ReAct 循环（工具调用回喂 + 历史裁剪）
│   ├── llm/                  LLM 客户端
│   │   ├── stream.py         httpx 解析 OpenAI SSE → 事件流
│   │   └── client.py         重试 + 熔断 + 连接池
│   ├── tools/                @tool 注册中心 + 内置工具（datetime/calculate/search/weather）
│   └── voice/__init__.py     ASR / TTS（OpenAI 兼容）
├── scripts/libs/             离线 wheel 包
├── tests/                    pytest 单元测试
├── web/                      Vue3 + Vite + TS 前端
│   ├── public/lib/vosk.js    Vosk WASM 语音唤醒引擎
│   ├── public/lib/wake-word.js
│   ├── public/models/vosk-model-small-cn-0.22/
│   └── src/
│       ├── App.vue / main.ts
│       ├── api.ts / audio.ts / types.ts
│       ├── components/FloatingAssistant.vue
│       └── composables/useApi.ts / useAssistant.ts
└── data/                     运行时数据（agent.log）
```

## 工具扩展

工具由**后端 `@tool` 注册中心**管理（`core/tools/`），前端只负责展示工具时间轴，
新增能力无需改动前端。ReAct 循环（`core/agent.py`）把工具 schema 注入 LLM，
执行结果回喂给模型，最终经 SSE 流式返回。

内置 4 个工具：

- `get_datetime` — 当前日期时间
- `calculate` — 安全算术（AST 白名单求值，禁 `eval`）
- `web_search` — duckduckgo 联网搜索
- `get_weather` — wttr.in 天气（免 key）

新增一个工具只需三步：

1. 新建 `core/tools/xxx.py`，用 `@tool("描述")` 装饰函数；参数带类型注解，
   schema 自动推导（同步/异步均可，如 `async def get_weather(city: str) -> str`）。
2. 在 `core/tools/__init__.py` 中 `import` 该模块触发注册。
3. 重启服务，LLM 会自动发现并调用新工具。
