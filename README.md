# 无限逻辑 · 语音全控智能体

用语音（或文字）控制电脑上的一切：唤醒 → 说话 → 意图判断 → 任务编排（澄清/确认/执行/汇报）→
多智能体协作 + 工具执行 → 记忆/RAG 上下文。纯浏览器 Vosk 离线唤醒 + 轻量 Python 后端（FastAPI），
OpenAI 兼容接口，支持离线/在线任意部署。

> 项目从「语音对话助手」演进而来，现已具备完整的 Agent 能力：自研编排状态机（不依赖 LangGraph/CrewAI）、
> 多智能体协调、长期记忆 + RAG、MCP 桥接、Skills 技能包、cron 定时任务、GUI/Shell/文件系统执行层。

## 功能

| 模块 | 功能 |
|------|------|
| 悬浮球助手 | 右下角可拖拽悬浮球，语音对话 + 聊天气泡面板 + 迷你播放条 |
| 语音唤醒 | 离线 Vosk WASM 唤醒词「小逻小逻」（含同音字变体匹配），纯浏览器运行 |
| 语音输入 | ASR（OpenAI 兼容）转文字，自动填入 |
| AI 对话 | LLM（OpenAI 兼容：DeepSeek / OpenAI / 通义…）多 profile 切换，ReAct 工具调用 |
| 任务编排 | 意图判断（闲聊/任务）→ 任务形成 → 澄清缺失信息 → 高风险操作确认 → 执行 → 汇报（SSE 实时） |
| 多智能体 | 复杂任务自动拆解：规划 / 执行 / 检索 / 批评 子代理并发协作（可开关） |
| 工具执行 | 27 个内置工具：搜索/天气/计算/文件/Shell/Python/GUI/记忆/定时/技能，@tool 自动注册 |
| 长期记忆 | 事实记忆（SQLite FTS5 全文检索）+ 任务后 LLM 自动提取 + RAG（BM25）检索注入上下文 |
| MCP 桥接 | 启动时连接外部 MCP server，工具动态注册进注册中心（mcp_<server>_<tool>） |
| Skills 技能包 | skills/*.yaml 热加载，{{param}} 填参逐步骤执行，危险技能需确认 |
| 定时任务 | cron（5 段）注册，到点无人值守执行（需澄清/确认的自动跳过） |
| 环境感知 | 采集系统信息写入 environment.md，注入规划上下文，工具参数贴合真实系统 |
| 全链路可控 | 任意时刻可停止整个任务/当前步骤（CancellationToken 贯穿到子进程，taskkill /T 兜底） |
| 安全审计 | 非 localhost 绑定强制 API Token；工具执行与高风险确认写入 data/audit.log |
| 语音播报 | 浏览器 SpeechSynthesis API 播报助手回复（可选后端 TTS） |
| 设置面板 | 控制台「设置」页：切换服务商 profile / 调节参数 / 设密钥（不回显）/ 检测连接，热重载即时生效 |
| 检测域 | `core/detection/`：环境感知 + 配置校验 + LLM/ASR/TTS 连通性三合一（`python main.py check` / 设置页「检测」） |

## 快速开始

```bash
# 1. 安装 Python 依赖（需要 Python 3.14+）
pip install -r requirements.txt
# 或双击 install_deps.bat — 在线优先，失败自动回退 scripts/libs/ 离线 wheel
#   （离线包按 Python 3.14 / win_amd64 打包，见 requirements.txt 顶部说明）

# 2. 配置（非敏感配置与密钥分离）
cp config.yaml.example config.yaml
cp config.secrets.yaml.example config.secrets.yaml
# 编辑 config.yaml（endpoint/model/多 profile 等非敏感项）与 config.secrets.yaml（密钥，不入库）。
# 密钥优先级：环境变量 > config.secrets.yaml：
#   set LLM_API_KEY=sk-...      # LLM（deepseek）
#   set ASR_API_KEY=sk-...      # ASR（MiMo 等 OpenAI 兼容服务）
#   set TTS_API_KEY=sk-...      # 后端 TTS（可选；默认浏览器本地语音播报）
# 配置也可在网页控制台「设置」页编辑（切换模型/调参/设密钥/检测连接，大部分即时生效）。

# 3. 启动（一键：前端 + 后端）
python main.py serve                  # 浏览器自动打开 http://127.0.0.1:8520
```

`python main.py serve` 同时提供前端页面（`web/dist`）与 `/api/*` 接口，打开一个端口即可使用。

**一键启动脚本**（Windows，含 LLM/ASR 连通性检查）：

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

- **双击悬浮球** 或点击面板内「👂 开启」启动语音唤醒
- 说 **「小逻小逻」**（含同音字变体）激活录音
- 录音 **VAD 静音检测自动停止**（默认静音 1.5s），最长 10s 上限
- 录音经 ASR 转文字 → 意图/任务编排 → 结果用浏览器 TTS 语音播报
- **语音回答提问**：助手提出需要确认/澄清的问题并播报完后，**直接开口说答案即可**（不必再说唤醒词）；
  能被选项回答的问题可说出选项文案（**仅精确匹配**，不做模糊解析）；也可继续用界面按钮/输入框作答
- **无应答进待机**：等待回答期间若一直没说话，超过 `vad.answer_timeout_ms`（默认 8s）进入待机；
  待机时唤醒词仍生效，说「小逻小逻」可**回到刚才那个提问**继续作答，而不是开新一轮
- **播报期间暂停监听**：助手说话时会短暂停掉唤醒引擎再恢复（不重载模型），避免它自己的声音触发唤醒
- 说出「停止 / 取消 / 暂停」等命令词可中断当前任务

唤醒词、静音阈值等可在 `config.yaml` 的 `voice.wake_word` / `voice.vad` 中调整。

> **桌面端说明**：桌面原生悬浮球（PySide6）与本地常驻语音监听已暂停开发，桌面代码迁移至 `desktop-ball` 分支（不再回迁）。
> 当前语音交互由浏览器端 Vosk WASM 唤醒 + 后端 ASR 承担。

## 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  交互层  浏览器悬浮球(Vue3 + Vosk WASM 唤醒) · ASR/TTS 播报     │
├──────────────────────────────────────────────────────────────┤
│  编排层  Orchestrator:会话状态机 → 意图 → 任务 → 澄清 → 确认    │
│          → 执行 → 汇报（SSE 事件流 + 人类在环问答通道）         │
│          └── StopController / CancellationToken 贯穿所有层     │
├──────────────────────────────────────────────────────────────┤
│  智能体层 Agent:协调者 + 规划/执行/检索/批评 子代理(并发≤4)     │
├──────────────────────────────────────────────────────────────┤
│  能力层  Tools · MCP · Skills · RAG · Memory · Scheduler       │
├──────────────────────────────────────────────────────────────┤
│  执行层  Shell · Python · 文件系统 · 环境感知 · GUI 自动化      │
└──────────────────────────────────────────────────────────────┘
```

一次输入的处理链路（`core/orchestrator/pipeline.py`）：

1. **意图判断** `judge_intent`：规则（记忆类陈述）+ LLM 结构化输出 → 闲聊 或 任务
2. **任务形成** `form_task`：LLM 提取 `{goal, params, missing, risk}`
3. **澄清** `run_clarify`：把 missing 转问题问操作者，回答后回填，循环至信息足够（上限 3 轮）
4. **确认** `confirm_if_needed`：risk=read 自动放行；write/exec 需操作者明确确认（无人值守默认拒绝）
5. **执行** `execute_task`：复杂任务转多智能体协调者；简单任务走 ReAct 循环
6. **汇报**：SSE 事件 `task_state(done)` 带 summary/steps；任务后异步提取事实写长期记忆

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /api/ping` | 健康检查 |
| `GET /api/config` | 配置概要（LLM/ASR/TTS profile、唤醒词、VAD） |
| `GET /api/tools` | 工具清单（@tool 注册中心的 OpenAI schema 数组，含 mcp_* 与 skill 工具） |
| `POST /api/voice/utter` | **编排入口**：文本 → SSE 事件流（task_state / content_delta / question / error / done）；body 可带 `session_id` 续接已有会话 |
| `POST /api/voice/answer` | 投递澄清/确认问题的回答（解除 ask() 阻塞） |
| `POST /api/task/{session_id}/stop` | 停止该会话整个任务（CancellationToken → executor/子进程中止） |
| `POST /api/tools/call` | 单工具执行（前端「重试失败工具」用） |
| `POST /api/voice/transcribe` | ASR 转写（JSON 体 audio_base64，16kHz mono WAV） |
| `GET /api/env` | 环境感知快照（environment.md 内容） |
| `GET /api/memory` · `DELETE /api/memory/{topic}` | 长期记忆浏览/删除 |
| `GET/POST /api/schedules` · `DELETE /api/schedules/{sid}` | 定时任务列表/注册/取消 |
| `POST/GET /api/sessions` · `PATCH/DELETE /api/sessions/{sid}` | 会话管理：新建/列表/重命名/删除；`POST /sessions/{sid}/clear` 清除上下文；`PATCH {archived}` 归档；`GET ?archived=` 过滤（可续接对话线） |
| `GET /api/config/full` | 设置页可编辑配置快照（密钥不回显，只报 `*_set`） |
| `PATCH /api/config` | 持久化非敏感配置并热重载（`restart_required` 标记服务器绑定类） |
| `PUT /api/config/secrets` | 设置/清除密钥（写 `config.secrets.yaml`，永不回显） |
| `GET /api/detection` | 聚合检测：环境感知 + 配置校验 + LLM/ASR/TTS 连通性 |

SSE 事件类型（`/api/voice/utter`）：

| 事件 | 含义 |
|------|------|
| `task_state` | 编排状态流转（understanding / notify / done，done 含 status/summary/steps） |
| `question` | 需要操作者回答，回答走 /api/voice/answer。`kind` 决定作答方式：`text` 自由文本 / `choice` 从 `options` 选 / `composite` 两者并存（任选其一） |
| `content_delta` / `reasoning_delta` | 文本 / 思考增量 |
| `tool_start` / `tool_end` | 工具开始 / 结束（tool_end 含 output 与 status） |
| `done` | 本轮完成 |
| `error` | 出错（含 message） |

## 命令

```
start.bat                   一键启动（Windows，含 LLM/ASR 连通性检查）
python main.py serve        启动 Web 服务（前端 + 后端 API）
python main.py check        聚合检测（环境 / 配置 / LLM·ASR·TTS 连通性）
```

## 测试

```
python -m pytest tests/ -q      # 后端单元测试（编排 / 工具 / 记忆 / RAG / MCP / Skills / 定时 / API）
python -m mypy core/ server.py  # 后端静态类型检查
cd web && npm run build         # 前端类型检查（vue-tsc）+ 生产构建
cd web && npm test              # 前端单元测试（Vitest）
```

### 前后端类型共享（openapi-typescript）

全部 JSON 端点均以 `response_model`（pydantic，见 `core/api/schemas.py`）声明 → FastAPI 自动生成
openapi.json → 前端 `openapi-typescript` 生成 `web/src/api/generated.ts`；`web/src/types.ts` 与
`web/src/api.ts` 的 **API 类型全部 re-export generated**（单一事实来源：后端 schema 改动 →
前端类型同步，避免手写漂移）。

**SSE 事件**（`/api/voice/utter`）不经 openapi：由 `core/orchestrator/events.py` 定义 pydantic
事件模型（pipeline/executor/voice 构造事件），前端 `web/src/types.ts` 手写对应类型
（`TaskStateEvent`/`ContentDeltaEvent`/… 及 `SseEvent` 联合），`api.ts` 的 streamUtter 类型化解析。
仅前端内部类型（`ToolStep`/`TokenUsage` 等）保留手写。

```bash
cd web && npm run gen:api   # 导出 openapi.json + 重新生成 generated.ts
```

修改后端响应模型后需重跑 `gen:api`；`generated.ts` 入库，`openapi.json` 为中间产物（gitignore）。

## 配置

配置采用 **pydantic 强类型校验 + 双文件分离**（非敏感配置 / 密钥独立存储），参考 InfiniteLogic-main 的强类型方案，保留多 profile YAML 结构：

- `config.yaml`：非敏感结构（llm / voice / server / mcp / rag / agent / llm_client / tools），**不含任何密钥**。
  加载时经 pydantic 模型校验（类型 / 范围 / 枚举，写错启动即报错）。多 profile（deepseek / openai / qwen）改 `active` 切换。
- `config.secrets.yaml`：密钥独立存储（`llm/asr/tts.api_key`、`server.api_token`），不入库；环境变量优先级更高。
- `voice.wake_word` / `voice.vad`：唤醒词与静音检测参数。
- `agent`：`recursion_limit`（ReAct 步数上限）、`multi_agent`（复杂任务是否转多智能体协调者）。
- `llm_client`：重试 / 熔断参数。
- `mcp.servers`：MCP server 列表（`{name, command, args}`），启动时自动连接并注册工具。
- `server.api_token`：非 localhost 绑定时的 API 访问令牌（留空则拒绝非 localhost 启动）。
- `server.cors_origins`：允许跨域的前端来源（默认空 = 禁止跨域）。
- `rag.auto_index`：启动时按需重建 RAG 索引（默认 true）。

**网页设置页**：控制台「设置」tab 可切换服务商 profile、调节参数、设置密钥（不回显）、检测连接；
保存后大部分配置**热重载即时生效**（LLM/ASR/TTS/唤醒词/参数），服务器绑定 / MCP 类变更需重启。

## 安全

- **绑定与令牌**：默认只绑定 `127.0.0.1`。将 `server.host` 改为非 localhost 地址时，必须设置
  `server.api_token`（否则拒绝启动）；此时所有 `/api/*` 请求需携带 `X-API-Token` 请求头。
- **CORS**：`server.cors_origins` 默认空 = 禁止跨域；本地同源/开发代理（vite 代理 /api）无需配置。
- **密钥零落库**：`config.yaml` 不含密钥，密钥在 `config.secrets.yaml` / 环境变量；API 永不回显密钥值，
  设置页只报「已设置 / 未设置」。
- **无沙箱 + 人类在环（策略可配）**：工具是否需要操作者确认由 `permissions` 策略决定（设置页「权限」可改），
  默认 **只读工具免询问、写入/执行工具需明确确认**；无人值守（定时任务）一律拒绝。
  **放宽策略即降低安全边界** —— 把 `exec` 层级设为 `allow` 等于让任意命令免确认执行，请确认你接受该风险。
  策略求值顺序：未注册工具 → 拒绝；任一 `deny` 规则短路（不可被后续规则翻案）；首条匹配规则；层级默认；`default_action`。
  注意边界：策略管的是**单个工具调用**；任务开始时仍有一次**计划级确认**（按 LLM 判定的任务风险），
  它不受 `permissions` 影响 —— 把 `exec` 设为 `allow` 只会免除逐工具的询问，不会免掉这次计划确认。
- **审计**：工具执行与高风险确认决策写入 `data/audit.log`（独立于 agent.log）。
- **凭据/环境**：`config.secrets.yaml`、`environment.md`（含本机信息）不入仓库；`package_deploy.bat` 打包时只带
  `config.yaml.example` / `config.secrets.yaml.example` 模板，不含任何密钥。

## 工具扩展

工具由**后端 `@tool` 注册中心**管理（`core/tools/`），前端只负责展示工具时间轴，
新增能力无需改动前端。工具分三类风险等级：`read`（自动执行）/ `write` / `exec`（需确认）。

内置工具：

| 类别 | 工具 |
|------|------|
| 基础 | `grep_file` `find_files` `read_file` `write_file` `parse_doc` `list_dir` `stat_path` `system_probe` |
| 执行 | `run_shell_tool` `run_python_tool`（超时/流式/可 kill，独立子进程） |
| 检索 | `web_search`（duckduckgo）`get_weather`（wttr.in 免 key）`get_datetime` `calculate`（AST 白名单求值） |
| 记忆 | `memory_get` `memory_put` |
| 定时 | `register_schedule` `list_schedules` `remove_schedule` |
| 技能 | `list_skills` `run_skill_tool` |
| GUI | `gui_activate_tool` `list_windows_tool` `gui_click_tool` `gui_type_tool` `gui_screenshot_tool`（懒加载优雅降级） |
| MCP | 动态注册 `mcp_<server>_<tool>`（需配置 `mcp.servers`） |

新增一个工具只需三步：

1. 新建 `core/tools/xxx.py`，用 `@tool("描述", risk="read|write|exec")` 装饰函数；参数带类型注解，
   schema 自动推导（同步/异步均可，如 `async def get_weather(city: str) -> str`）。
2. 在 `core/tools/__init__.py` 中 `import` 该模块触发注册。
3. 重启服务，LLM 会自动发现并调用新工具。

## 目录结构

```
无限逻辑-语音全控智能体/
├── main.py / server.py        入口 + FastAPI 装配（lifespan + 认证 + 静态托管 + 挂载路由）
├── start.bat / install_deps.bat / package_deploy.bat
├── config.yaml.example        非敏感配置模板（不含密钥）
├── config.secrets.yaml.example 密钥存储模板（复制为 config.secrets.yaml，不入库）
├── requirements.txt           Python 依赖（在线 / 离线 scripts/libs/ 双路）
├── mypy.ini                   后端静态类型检查配置
├── core/
│   ├── config/                配置包：schema（pydantic 模型）/ loader（YAML+密钥注入）/ runtime（单例+热重载）/ constants
│   ├── logger.py              loguru 日志（控制台 + data/agent.log）+ 审计（data/audit.log）
│   ├── detection/             检测域：environment（环境感知）/ validator（配置校验）/ connectivity（LLM/ASR/TTS 连通性）
│   ├── api/                   API 路由（voice / tools / memory / schedule / settings / state 会话注册表）
│   ├── llm/                   LLM 客户端（stream.py SSE 解析 / client.py 重试+熔断+连接池）
│   ├── voice/                 ASR / TTS（OpenAI 兼容）
│   ├── orchestrator/          编排层：session / intent / task / clarify / confirm / executor / control / pipeline
│   ├── agent/                 base 子代理基座 + coordinator 多智能体协调者
│   ├── tools/                 @tool 注册中心 + 内置工具（base / basic / calculator / datetime_tool /
│   │                          search / weather / memory_tools / schedule_tools / skill_tools / gui_tools / mcp_bridge）
│   ├── execution/             执行层：shell（可 kill 进程树）/ python（独立进程）/ fs（通用格式读写）/ gui（自动化）
│   ├── memory/                长期事实记忆（facts.sqlite FTS5 全文检索）+ 任务后提取（extract.py）+ 上下文注入（context.py）
│   ├── rag/                   索引（indexer.py 分块）+ 检索（retriever.py BM25 打分）
│   ├── mcp/                   外部 MCP server 客户端（client.py stdio）+ 生命周期（manager.py）
│   ├── skills/                技能包加载（loader.py 热重载）+ 执行（executor.py）
│   └── scheduler/             cron 定时（scheduler.py 持久化）+ 无人值守执行（runner.py）
├── skills/                    技能定义（YAML，文件名 = 技能名）
├── memory/                    长期记忆数据（facts.sqlite）
├── rag/                       RAG 索引数据（index.db）
├── environment.md             环境感知快照（core/detection/environment.py 生成，agent 规划时注入，gitignore 不入仓库）
├── data/                      运行时数据（agent.log / audit.log / schedules.json / tasks/ 等）
├── scripts/                   辅助脚本（mcp_echo_server.py / verify_memory.py）+ 离线 wheel
├── scripts/libs/              离线 wheel 包
├── tests/                     pytest 单元测试（编排 / 工具 / 记忆 / RAG / MCP / Skills / 定时 / API）
├── web/                       Vue3 + Vite + TS 前端
│   ├── public/lib/vosk.js     Vosk WASM 语音唤醒引擎
│   ├── public/lib/wake-word.js
│   ├── public/models/vosk-model-small-cn-0.22/
│   └── src/
│       ├── App.vue / main.ts / router.ts / api.ts / types.ts
│       ├── components/FloatingAssistant.vue + assistant/（悬浮球面板组件）
│       ├── components/console/（控制台：任务/记忆/环境/定时/工具视图）
│       ├── components/ui/     ui/ 原语组件（UiButton/UiInput/UiSelect/UiToggle/UiCard/UiModal 等 + 语义令牌）
│       ├── composables/        useApi.ts / useAssistant.ts / useAssistantVisuals.ts / useConsole.ts
│       └── views/              StartPage.vue / ConsolePage.vue
└── deploy/                     打包发布副本（package_deploy.bat 生成；含 deploy.zip）
```
