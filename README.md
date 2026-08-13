# 无限逻辑 · 语音全控智能体

用语音（或文字）控制电脑上的一切：唤醒 → 说话 → 意图判断 → 任务编排（澄清/确认/执行/汇报）→
多智能体协作 + 工具执行 → 记忆/RAG 上下文。纯浏览器 Vosk 离线唤醒 + 轻量 Python 后端（FastAPI），
OpenAI 兼容接口，支持离线/在线任意部署。

> 项目从「语音对话助手」演进而来，现已具备完整的 Agent 能力：自研编排状态机（不依赖 LangGraph/CrewAI）、
> 多智能体协调、长期记忆 + RAG、MCP 桥接、Skills 技能包、cron 定时任务、GUI/Shell/文件系统执行层。
> 整体架构见 `docs/architecture/01-voice-control-agent.md`，实施进度见 `docs/architecture/roadmap.md`。

## 功能

| 模块 | 功能 |
|------|------|
| 悬浮球助手 | 右下角可拖拽悬浮球，语音对话 + 聊天气泡面板 + 迷你播放条 |
| 语音唤醒 | 离线 Vosk WASM 唤醒词「小逻小逻」（含同音字变体匹配），纯浏览器运行 |
| 语音输入 | ASR（OpenAI 兼容）转文字，自动填入 |
| AI 对话 | LLM（OpenAI 兼容：DeepSeek / OpenAI / 通义…）多 profile 切换，ReAct 工具调用 |
| 任务编排 | 意图判断（闲聊/任务）→ 任务形成 → 澄清缺失信息 → 高风险操作确认 → 执行 → 汇报（SSE 实时） |
| 多智能体 | 复杂任务自动拆解：规划 / 执行 / 检索 / 批评 子代理并发协作（可开关） |
| 工具执行 | 26 个内置工具：搜索/天气/计算/文件/Shell/Python/GUI/记忆/定时/技能，@tool 自动注册 |
| 长期记忆 | 事实记忆（SQLite）+ 任务后 LLM 自动提取 + 关键词 RAG 检索注入上下文 |
| MCP 桥接 | 启动时连接外部 MCP server，工具动态注册进注册中心（mcp_<server>_<tool>） |
| Skills 技能包 | skills/*.yaml 热加载，{{param}} 填参逐步骤执行，危险技能需确认 |
| 定时任务 | cron（5 段）注册，到点无人值守执行（需澄清/确认的自动跳过） |
| 环境感知 | 采集系统信息写入 environment.md，注入规划上下文，工具参数贴合真实系统 |
| 全链路可控 | 任意时刻可停止整个任务/当前步骤（CancellationToken 贯穿到子进程，taskkill /T 兜底） |
| 语音播报 | 浏览器 SpeechSynthesis API 播报助手回复（可选后端 TTS） |

## 快速开始

```bash
# 1. 安装 Python 依赖（需要 Python 3.14+）
pip install -r requirements.txt
# 或双击 install_deps.bat — 在线优先，失败自动回退 scripts/libs/ 离线 wheel
#   （离线包按 Python 3.14 / win_amd64 打包，见 requirements.txt 顶部说明）

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

- **双击悬浮球** 或点击面板内「👂 开启」启动语音唤醒
- 说 **「小逻小逻」**（含同音字变体）激活录音
- 录音 **VAD 静音检测自动停止**（默认静音 1.5s），最长 10s 上限
- 录音经 ASR 转文字 → 意图/任务编排 → 结果用浏览器 TTS 语音播报
- 说出「停止 / 取消 / 暂停」等命令词可中断当前任务

唤醒词、静音阈值等可在 `config.yaml` 的 `voice.wake_word` / `voice.vad` 中调整。

> **桌面端说明**：桌面原生悬浮球（PySide6）与本地常驻语音监听（`core/voice/wake.py`）的开发已暂停，
> 桌面代码迁移至 `desktop-ball` 分支（不再回迁）。当前语音交互由浏览器端 Vosk WASM 唤醒 + 后端 ASR 承担；
> `core/voice/wake.py` 保留为可复用模块（`scripts/voice_smoke.py` 冒烟、`tests/test_voice_wake.py` 测试），未接入 server 运行链路。

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
| `POST /api/ai/chat` | SSE 流式聊天（ReAct + 工具，旧入口） |
| `POST /api/voice/utter` | **编排入口**：文本 → SSE 事件流（task_state / content_delta / question / error / done） |
| `POST /api/voice/answer` | 投递澄清/确认问题的回答（解除 ask() 阻塞） |
| `POST /api/task/{session_id}/stop` | 停止该会话整个任务（CancellationToken → executor/子进程中止） |
| `POST /api/tools/call` | 单工具执行（前端「重试失败工具」用） |
| `POST /api/voice/transcribe` | ASR 转写（JSON 体 audio_base64，16kHz mono WAV） |
| `GET /api/env` | 环境感知快照（environment.md 内容） |
| `GET /api/memory` · `DELETE /api/memory/{topic}` | 长期记忆浏览/删除 |
| `GET/POST /api/schedules` · `DELETE /api/schedules/{sid}` | 定时任务列表/注册/取消 |

SSE 事件类型（`/api/voice/utter`、`/api/ai/chat`）：

| 事件 | 含义 |
|------|------|
| `task_state` | 编排状态流转（understanding / notify / done，done 含 status/summary/steps） |
| `question` | 需要操作者回答（澄清/确认），回答走 /api/voice/answer |
| `content_delta` / `reasoning_delta` | 文本 / 思考增量 |
| `tool_start` / `tool_end` | 工具开始 / 结束（tool_end 含 output 与 status） |
| `done` | 本轮完成 |
| `error` | 出错（含 message） |

## 命令

```
start.bat                   一键启动（Windows，含 LLM/ASR 连通性测试）
python main.py serve        启动 Web 服务（前端 + 后端 API）
python main.py test         测试 LLM / ASR 连通性
```

## 测试

```
python -m pytest tests/ -q   # 后端单元测试（编排 / 工具 / 记忆 / RAG / MCP / Skills / 定时 / API）
cd web && npm run build      # 前端类型检查（vue-tsc）+ 生产构建
```

## 配置

`config.yaml.example` 为完整模板，支持 `${ENV_VAR}` 环境变量插值。核心段：

- `llm`：OpenAI 兼容 LLM，多 profile（deepseek / openai / qwen），改 `active` 切换。
- `voice.asr`：OpenAI 兼容 ASR（endpoint/model 自填，DeepSeek 无 ASR 服务）。
- `voice.tts`：可选后端 TTS；默认用浏览器 SpeechSynthesis 播报。
- `voice.wake_word` / `voice.vad`：唤醒词与静音检测参数。
- `agent`：`recursion_limit`（ReAct 步数上限）、`multi_agent`（复杂任务是否转多智能体协调者）。
- `llm_client`：重试 / 熔断参数。
- `mcp.servers`：MCP server 列表（`{name, command, args}`），启动时自动连接并注册工具。

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
├── main.py / server.py        入口 + FastAPI 宿主（/api/* + 托管 web/dist 前端 + SSE）
├── start.bat / install_deps.bat / package_deploy.bat
├── config.yaml.example        配置模板
├── requirements.txt           Python 依赖（在线 / 离线 scripts/libs/ 双路）
├── core/
│   ├── config.py              配置加载（YAML + ${ENV} 插值 + 多 profile + 默认值兜底）
│   ├── logger.py              loguru 日志（控制台 + data/agent.log）
│   ├── llm/                   LLM 客户端（stream.py SSE 解析 / client.py 重试+熔断+连接池）
│   ├── voice/                 ASR / TTS（OpenAI 兼容）；wake.py 桌面监听（保留，未接入）
│   ├── orchestrator/          编排层：session / intent / task / clarify / confirm / executor / control / pipeline
│   ├── agent/                 base 子代理基座 + coordinator 多智能体协调者（legacy.py 为旧 ReAct）
│   ├── tools/                 @tool 注册中心 + 内置工具（base / basic / calculator / datetime_tool /
│   │                          search / weather / memory_tools / schedule_tools / skill_tools / gui_tools / mcp_bridge）
│   ├── execution/             执行层：shell（可 kill 进程树）/ python（独立进程）/ fs（通用格式读写）/
│   │                          gui（自动化）/ envprobe（环境感知 → environment.md）
│   ├── memory/                长期事实记忆（facts.sqlite）+ 任务后提取（extract.py）+ 上下文注入（context.py）
│   ├── rag/                   索引（indexer.py 分块）+ 检索（retriever.py 关键词打分）
│   ├── mcp/                   外部 MCP server 客户端（client.py stdio）+ 生命周期（manager.py）
│   ├── skills/                技能包加载（loader.py 热重载）+ 执行（executor.py）
│   └── scheduler/             cron 定时（scheduler.py 持久化）+ 无人值守执行（runner.py）
├── skills/                    技能定义（YAML，文件名 = 技能名）
├── memory/                    长期记忆数据（facts.sqlite）
├── rag/                       RAG 索引数据（index.db）
├── environment.md             环境感知快照（envprobe 生成，agent 规划时注入）
├── data/                      运行时数据（agent.log / schedules.json / 截图等）
├── scripts/                   辅助脚本（voice_smoke.py / mcp_echo_server.py / verify_memory.py）+ 离线 wheel
├── scripts/libs/              离线 wheel 包
├── tests/                     pytest 单元测试（30 个文件）
├── web/                       Vue3 + Vite + TS 前端
│   ├── public/lib/vosk.js     Vosk WASM 语音唤醒引擎
│   ├── public/lib/wake-word.js
│   ├── public/models/vosk-model-small-cn-0.22/
│   └── src/
│       ├── App.vue / main.ts / router.ts / api.ts / types.ts
│       ├── components/FloatingAssistant.vue + assistant/（悬浮球面板组件）
│       ├── components/console/（控制台：任务/记忆/环境/定时/工具视图）
│       ├── composables/        useApi.ts / useAssistant.ts / useAssistantVisuals.ts
│       └── views/              StartPage.vue / ConsolePage.vue
├── deploy/                     打包发布副本（package_deploy.bat 生成；含 deploy.zip）
└── docs/                       架构设计 + 分阶段实施计划
```

## 相关文档

- [整体架构设计](docs/architecture/01-voice-control-agent.md) — 分层设计、核心流程、安全与信任模型、技术选型
- [实施路线追踪](docs/architecture/roadmap.md) — P0 地基 / P1 记忆+RAG / P2 MCP+Skills / P3 多智能体+定时+GUI
- [P0 计划](docs/superpowers/plans/2026-08-12-agent-p0-foundation.md) · [P1 计划](docs/superpowers/plans/2026-08-12-agent-p1-memory-rag.md) ·
  [P2 计划](docs/superpowers/plans/2026-08-12-agent-p2-capabilities.md) · [P3 计划](docs/superpowers/plans/2026-08-12-agent-p3-advanced.md)
