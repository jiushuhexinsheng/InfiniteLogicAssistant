# 无限逻辑 · 语音全控智能体 —— 整体架构设计

> 版本 v1 · 2026-08-12 · 目标：用语音控制电脑上的一切，无沙箱/安全区，全链路可观测、可中止。
> 决策基线：**后端宿主 + 浏览器面板 + 语音交互**；**自研轻量编排**（不引入 LangGraph/CrewAI 等重框架）。
>
> ## 实现状态（2026-08 更新）
>
> P0–P3 已全部完成并合入主分支（见 `roadmap.md`）。**桌面语音监听已暂停开发、不再回迁**：
> 桌面悬浮球 UI 代码迁移至 `desktop-ball` 分支（桌面常驻监听已一并移除）。
> 当前语音交互 = **浏览器 Vosk WASM 唤醒 + 后端 OpenAI 兼容 ASR/TTS + SpeechSynthesis 播报**。
> 下文涉及「桌面常驻语音监听」的段落均为设计意图/历史说明，与当前主分支实现存在差异。

> ## 与当前实现的差异（2026-08-30 同步，以代码为准）
>
> 本文撰写于实现之前，以下设计点已按落地方式调整：
> - **提示词集中管理**：原 `prompts/` 目录未落地；系统提示集中在 `core/prompts.py` 常量模块
>   （`CHIT_CHAT_SYSTEM`/`INTENT_SYSTEM`/`FORM_TASK_SYSTEM`/`EXECUTOR_SYSTEM`/`ROLE_PROMPTS`/
>   `DECOMPOSE_SYSTEM`），各编排模块 import 引用，无热编辑。
> - **子代理合一**：规划/执行/检索/批评不再各自独立文件，统一由 `core/agent/base.py`
>   的 `run_subagent` 按角色 prompt 分派；`critic` 只把审查意见追加到摘要，**不打回重做**。
> - **环境感知**：`execution/envprobe.py` → `core/detection/environment.py`，只产出
>   `environment.md`（无 `env_cache.json`）。
> - **记忆两级**：长期记忆落地为 `core/memory/facts.py`（SQLite FTS5 trigram 事实存储）
>   + `extract.py`（任务后提取）+ `context.py`（检索注入）；向量记忆与 `memory/vectors`、
>   `memory/notes/` 未落地。
> - **RAG 检索**：`core/rag/retriever.py` 采用 **BM25 打分**（非 TF-IDF）。
> - **停止层级**：`StopController` 落地为 `stop_task()`（取消整任务 + token 贯穿），
>   无独立的 stop_step / pause。
> - **风险分级**：任务/工具风险为 **read / write / exec** 三级（非 low/medium/high）。
> - **会话落盘**：交互会话与定时任务均经 `core/api/state.py::persist` 落盘到
>   `data/tasks/<id>.json` + `data/history.db`（控制台「历史」tab），无 `data/sessions/`。
> - **MCP 桥**：`core/tools/mcp_bridge.py` 由 `core/mcp/manager.py` 在启动时注册工具，
>   不在 `core/tools/__init__.py` 导入。
> - **TTS 实现**在 `core/tts.py`（顶层），ASR 在 `core/voice/__init__.py`；无 `vad.py`
>   （VAD 静音检测在浏览器端）。
> - **目录即架构**见 §2 更新后的结构图。

---

## 0. 设计目标与原则

| 目标 | 说明 |
|------|------|
| 语音全控 | 唤醒 → 说话 → 判断意图 → 形成任务 → 澄清 → 确认 → 执行 → 汇报；一切可语音触发 |
| 无沙箱 | 不设安全区；以「人类在环确认 + 审计」替代强制沙箱（见 §6） |
| 模块极清 | 每个模块单一职责、可独立测试、可插拔；目录即架构 |
| 全链路可控 | 任何时刻可停止整个任务/当前进程；流式可观测（复用 SSE） |
| 自研轻量 | 编排自写，复用现有 `core/llm`、`@tool` 注册中心、Vue 控制台 |

---

## 1. 总体架构（分层总览）

```
┌──────────────────────────────────────────────────────────────┐
│  交互层  Voice（浏览器唤醒/ASR/TTS）· Web 控制台（Vue）      │
├──────────────────────────────────────────────────────────────┤
│  编排层  Orchestrator：会话 → 意图 → 任务 → 澄清 → 确认 → 执行 │
│          └── 停止/中止控制器（贯穿所有层）                     │
├──────────────────────────────────────────────────────────────┤
│  智能体层 Agent：协调者 + 规划 / 执行 / 检索 / 批评 子代理       │
├──────────────────────────────────────────────────────────────┤
│  能力层  Tools · MCP · Skills · RAG · Memory · Scheduler       │
├──────────────────────────────────────────────────────────────┤
│  执行层  Shell · Py · 文件系统 · 环境感知 · GUI(可选)           │
└──────────────────────────────────────────────────────────────┘
```

数据流方向：
- 下行：交互层文本 → 编排层 → 智能体层 → 能力层 → 执行层
- 上行：执行结果/工具输出 → 回喂智能体 → 编排层汇报 → 交互层（TTS/面板 SSE）
- 横切：**CancellationToken**（停止）与**审计日志**贯穿所有层

---

## 2. 模块拆分（目录即架构）

```
无限逻辑-语音全控智能体/
├── main.py                     # 入口：serve / test（连通性检测）
├── server.py                   # FastAPI 宿主：/api/* + SSE + 静态托管 + SPA 兜底
├── start.bat / install_deps.bat / package_deploy.bat
├── config.yaml.example         # 非敏感配置模板（不含密钥）
├── config.secrets.yaml.example # 密钥存储模板（复制为 config.secrets.yaml，不入库）
├── environment.md              # ★ 环境感知快照（core/detection/environment.py 生成）
├── core/
│   ├── config/                 # 配置包：schema（pydantic 模型）/ loader（YAML+密钥注入）/
│   │                           #   runtime（单例+热重载）/ constants
│   ├── logger.py               # 日志（loguru）+ 审计（data/audit.log）
│   ├── detection/              # ★ 检测域：environment（环境感知）/ validator（配置校验）/
│   │                           #   connectivity（LLM/ASR/TTS 连通性）
│   ├── api/                    # FastAPI 路由：voice / tools / memory / schedule / settings /
│   │                           #   history / providers / state（会话注册表+落盘）
│   ├── llm/                    # LLM 客户端：stream（SSE 解析）/ client（重试+熔断+连接池+failover）
│   ├── voice/                  # 语音层：ASR（__init__.py）+ TTS（tts.py，OpenAI 兼容双协议）
│   ├── orchestrator/           # ★ 编排层（核心，全部自研）
│   │   ├── session.py          #   会话状态机与管理
│   │   ├── intent.py           #   意图判断：闲聊 or 任务（结构化输出）
│   │   ├── task.py             #   任务形成：goal / params / missing / risk
│   │   ├── clarify.py          #   澄清循环：把缺失信息转问题，等操作者回答
│   │   ├── confirm.py          #   高风险操作确认（工具实际风险 read/write/exec）
│   │   ├── executor.py         #   执行循环：plan → act → observe → reflect
│   │   ├── control.py          #   ★ 停止控制器（CancellationToken → stop_task）
│   │   ├── pipeline.py         #   编排主链：意图→任务→澄清→确认→执行→汇报（SSE）
│   │   └── events.py           #   SSE 事件模型（task_state/tool_start/question/done...）
│   ├── agent/                  # ★ 多智能体
│   │   ├── coordinator.py      #   协调者：LLM 拆解/分派（独立并发≤4）/critic 审查/合并
│   │   └── base.py             #   子代理统一基座：run_subagent（按角色 prompt 分派）
│   ├── tools/                  # ★ 工具注册中心（@tool）+ 内置工具（basic/calculator/
│   │                           #   datetime_tool/search/weather/memory_tools/schedule_tools/
│   │                           #   skill_tools/gui_tools/mcp_bridge）
│   ├── execution/              # ★ 执行层：shell（进程树 kill）/ python（独立进程）/
│   │                           #   fs（通用格式读写）/ gui（pyautogui 懒加载）
│   ├── memory/                 # 长期事实记忆：facts.py（SQLite FTS5 trigram）+
│   │                           #   extract.py（任务后提取）+ context.py（检索注入）
│   ├── rag/                    # 索引（indexer.py 分块）+ 检索（retriever.py BM25 打分）+ tokenize
│   ├── mcp/                    # 外部 MCP 客户端（client.py stdio）+ 生命周期（manager.py 注册工具）
│   ├── skills/                 # 技能包加载（loader.py 热重载）+ 执行（executor.py）
│   ├── scheduler/              # cron 定时（scheduler.py 持久化）+ 无人值守执行（runner.py 落盘历史）
│   ├── session/                # 会话域：会话历史落盘（history.py → data/history.db）
│   ├── prompts.py              # 系统提示词集中管理（单一来源）
│   └── vendors.py              # 多 provider 协议分派（openai/anthropic/gemini）
├── skills/                     # 技能定义（YAML，文件名 = 技能名）
├── memory/                     # 长期记忆数据（facts.sqlite）
├── rag/                        # RAG 索引数据（index.db）
├── data/                       # 运行时数据（agent.log / audit.log / history.db / schedules.json / tasks/）
├── scripts/                    # 辅助脚本 + 离线 wheel（scripts/libs/，Python 3.14 win_amd64）
├── tests/                      # pytest 单元测试
├── web/                        # Vue3 + Vite + TS 前端（悬浮球 + 控制台 + ui/ 原语组件）
│   └── public/lib/vosk.js + wake-word.js + models/   # Vosk WASM 离线唤醒
└── deploy/                     # 打包发布副本（package_deploy.bat 生成，含 deploy.zip）
```

`★` = 本次新增/重构的重点模块。

---

## 3. 各层模块设计

### 3.1 交互层：语音 + 前端

**语音（当前实现：浏览器端）**——Vosk WASM 唤醒词在浏览器内运行，ASR/TTS 走后端 OpenAI 兼容接口：
- 浏览器端 `public/lib/vosk.js` + `wake-word.js`：离线唤醒词「小逻小逻」（含同音字变体），激活录音后经 ASR 转文字。
- ~~桌面常驻监听（本地 Vosk 后台常驻麦克风）~~：设计目标之一，**已暂停开发并移除**（代码在 `desktop-ball` 分支）；若未来恢复，可复用浏览器 WASM 方案作降级。
- **ASR**：`core/voice/__init__.py` 的 `ASRClient`（OpenAI 兼容多提供方，async httpx，POST
  `{endpoint}{chat_path}` + `messages[0].content` input_audio；小米 MiMo 等厂商预设通过
  `profile.compat` 开关适配认证头/audio_data_url/language）。
- **TTS**：`core/tts.py`（顶层），支持 OpenAI 兼容 **speech**（`/v1/audio/speech`）与
  **chat**（`messages + audio{format, voice}`，MiMo TTS 系列含音色复刻/描述）双协议；
  浏览器端继续 SpeechSynthesis 作面板播报。
- 语音事件统一转成文本推入编排层；**停止/取消**由前端识别后调用
  `POST /api/task/{session_id}/stop` 直接触发 `StopController`，不经过 LLM（保证响应及时）。

**前端（Vue 控制台）**：复用现有悬浮球 + /console，新增视图：任务列表/单任务执行流、待澄清问题卡片、记忆浏览、环境快照、定时任务、审计日志。SSE 复用现有 `stream_chat` 的事件通道，新增事件类型 `task_state`/`question`/`confirm`/`stop_ack`。

### 3.2 编排层（核心，全部自研）

**会话状态机** `session.py`：

```
idle ──唤醒/输入──▶ understanding ──闲聊──▶ chit_chat ──▶ idle
                        │
                        ▼ 是任务
                  forming_task ──▶ clarifying ──(提问/等答)──▶ confirming ──▶ executing ──▶ reporting ──▶ idle
                        │                                                     │
                        └────────── 任何状态 ◀── stop / pause / cancel ◀─────┘
```

**intent.py（意图判断）**：用结构化输出（现有 tool-calling 机制）让 LLM 输出 `{type: chit_chat | task, summary, task_type}`。闲聊直接回复；任务进入 task.py。

**task.py（任务形成）**：LLM 结构化提取 `{goal, params, missing: [需要问操作者的信息], risk: read|write|exec}`。这是"先对话判断是否需要形成任务、需要问什么"的关键一步。

**clarify.py（澄清循环）**：把 `missing` 转成自然语言问题（"想对哪个文件操作？删除还是移动？"），通过语音/面板问操作者，**阻塞等待回答**；收到回答后回填参数，循环直到 `missing` 为空。每轮带最多提问次数上限，防止无限追问。

**confirm.py（确认层）**：确认决策基于**工具实际风险**（`TOOLS.risk`，而非任务声明的 risk，避免任务被误标 read 时高风险工具无确认执行）。
`read`（只读）自动放行；`write`/`exec`（删除/覆盖/执行任意命令等）需操作者明确确认；
无人值守（定时任务）或模糊回答默认**拒绝**。用户可回"确认/执行/可以"等确认词。

**executor.py（执行循环）**：核心循环，即"循环工程"的实现载体：
```
plan（拆步骤）→ 每步：选工具/子代理 → act → observe（工具结果）→ reflect（是否达成目标）
收敛判定：目标达成 / 步数超限 / 连续失败 / 用户 stop
失败重试：区分可重试（网络/暂时）与不可重试（参数错→回澄清）
```

**control.py（停止/中止）★**：
- `StopController.stop_task()` 取消共享 `CancellationToken`，贯穿 executor → 每个工具调用 → 每个子进程。
- 各执行点（`throw_if_cancelled` / `is_cancelled`）检查 token，执行层子进程（`run_shell`）中止时
  OS 级 kill 进程树（Windows `taskkill /T`）兜底。
- 取消统一收敛为 `status=stopped` 返回，调用方无需捕获 `CancelledError`。
- 触发源：面板按钮 / 前端命令词（`POST /api/task/{session_id}/stop`）。

### 3.3 智能体层：多智能体协作

- **coordinator.py**：把任务分解为子任务（LLM 结构化拆解，`decompose` 工具返回
  `{goal, agent_type, independent}`），给每个子任务选子代理；`independent` 的子任务并发
  （`asyncio.gather` + `Semaphore(4)`），依赖子任务串行；全部完成后跑 critic 审查合并。
  复杂任务判定在 `orchestrator/executor.py::should_use_multi_agent`（启用且多参数/长目标）。
- **子代理统一基座 `agent/base.py`**（每个都是一次 LLM 循环，共享 Tools/RAG/Memory）：
  - `planner`：把目标转成有序步骤 + 前置条件。
  - `doer`：执行具体步骤，调工具，把结果回喂。
  - `searcher`：检索（RAG/网络/文件），供 doer 引用。
  - `critic`：对子代理结果自检（是否达到目标/有无遗漏），**把审查意见追加到摘要**，不打回重做。
  - 角色切换 = `run_subagent(role_prompt, goal, ...)` 传入不同角色 prompt，无独立文件。
- **结果聚合**：协调者把各子代理 `{goal, agent_type, status, output, tools}` 合并为摘要，
  前端以 `agent:<type>` 步骤在 SSE 工具时间轴展示；会话在结束时由 `state.persist`
  落盘到 `data/tasks/<id>.json`。

### 3.4 能力层

**Tools（基础工具，够底层）**：复用现有 `@tool` 注册中心（`core/tools/base.py`）。基础集见 §附录A。工具分三类：只读（自动执行）、写（需 confirm 策略）、执行（需 confirm 策略）。

**MCP**：`mcp/client.py` 连接外部 MCP server（filesystem/git/browser/数据库/浏览器控制等），把 MCP 工具动态注册进 `TOOLS`（`tools/mcp_bridge.py`），对编排层透明。

**Skills（能力包）**：`skills/*.yaml` 定义：`name / description / requires / steps(模板) / validate / dangerous`。执行时 Skill 展开为一串工具步骤模板，由 doer 填充参数。热加载（`skills/loader.py` 监听目录）。

**RAG**：索引源 = environment.md、用户文档目录、代码库、（可选）历史对话。`core/rag/indexer.py`
分块建索引（sqlite index.db），`core/rag/retriever.py` 用 **BM25 打分**检索 top-k 片段注入上下文。

**Memory（当前两级）**：
| 级 | 存什么 | 存哪 | 何时写 |
|----|--------|------|--------|
| 短期 | 当前会话消息/工具结果 | 内存 session | 实时 |
| 长期·事实 | 用户偏好、常用路径、环境结论 | `memory/facts.sqlite`（FTS5 trigram 全文检索） | 任务结束后 LLM 提取（`core/memory/extract.py`） |

（长期·向量记忆 `memory/vectors` 未落地，见顶部「与当前实现的差异」。）

读取：执行前把相关事实（按当前任务主题检索）经 `core/memory/context.py::build_context` 注入系统提示。

**Scheduler（定时任务）**：cron 式注册（`data/schedules.json`，可语音注册"每天九点查天气"）。
后台循环到点触发 `core/scheduler/runner.py::run_scheduled`（无人值守：需澄清/确认的任务经
`_SilentChannel` 自动拒绝，只读任务直接执行）→ 结果落盘会话历史（控制台「历史」可见）；
**存在被跳过的高风险操作时记 warning 提醒**。支持一次性提醒与周期任务。

### 3.5 执行层

- **shell.py**：`subprocess` 封装——超时、流式 stdout 捕获、**可中止**（kill 进程树）、cwd/环境变量控制。是"Shell 控制"的基础。
- **python.py**：执行 .py 脚本（独立子进程，避免污染宿主；`sys.executable` 隔离）。
- **fs.py**：读写**所有通用格式**：text / json / yaml / toml / md / csv / xlsx / sqlite / ini / env；每个格式一个 reader/writer 分发器；写前快照（可选）支持回滚。
- **environment.py（环境感知，`core/detection/`）★**：见 §4.1。
- **gui.py（可选）**：pyautogui/win32——鼠标点击/键盘输入/窗口激活/截图，实现"控制 GUI 应用"。

---

## 4. 核心流程

### 4.1 环境感知调查（`core/detection/environment.py`）

```
安装/首次运行 / 前端「检测」或 python main.py test → environment.py 全量调查：
  OS 版本/架构/主机名 · CPU/内存/磁盘 · 已装软件与常用命令
  网络与代理 · PATH/默认 Shell · 桌面/文档/下载路径
  浏览器/编辑器/Python 版本 · 可用的 LLM/ASR/TTS provider
→ 结构化 + 自然语言写入 environment.md（独立文件，前端/执行层/RAG 都读它）
可随时触发：`python main.py test` / 控制台「检测」/ 任务前按需 → 重新 probe 并合并增量到 environment.md
```

agent 每次规划时把 `environment.md`（或其相关段）注入上下文，让工具参数（路径、命令）贴合真实系统。

### 4.2 语音 → 任务 → 执行 → 汇报 闭环

```
1. 唤醒 → ASR → 文本
2. intent.py：闲聊 or 任务？
    闲聊 → LLM 回复 → TTS 播报（不进入任务）
3. task.py：形成任务 {goal, params, missing, risk}
4. clarify.py：把 missing 作为问题问操作者，等回答，循环到信息足够（上限 3 轮）
5. confirm.py：risk=write/exec 先复述方案，确认后执行（基于工具实际风险）
6. coordinator + executor：复杂任务拆子任务 → 子代理并发 → 工具 → 回喂 → 收敛；简单任务走 ReAct
7. reporting：SSE 流式结果摘要（前端 TTS 播报）；面板展示完整执行流
任何时刻："停止/取消" → `POST /api/task/{session_id}/stop` → control.py 立即中止
```

### 4.3 停止 / 中止机制

- **令牌贯穿**：`CancellationToken` 从会话 → 任务 → 工具 → 子进程；每个 await 点检查 `is_cancelled`。
- **单级停止**：`StopController.stop_task()` 取消共享 token；执行层子进程中止时 kill 进程树。
- **收敛**：取消统一转为 `status=stopped` 返回（executor / coordinator 均已处理），无 paused 恢复机制。
- **兜底**：执行层 kill 不了时 OS 级强杀（`taskkill /T`）；工具执行与确认决策写入 `data/audit.log`。

---

## 5. 工程方法论：提示词 / 驾驭 / 循环

### 提示词工程
- 系统提示集中在 `core/prompts.py` 常量模块（单一来源）：
  - `CHIT_CHAT_SYSTEM`（闲聊）· `INTENT_SYSTEM`（意图判断）· `FORM_TASK_SYSTEM`（任务形成）
  - `EXECUTOR_SYSTEM`（ReAct 执行）· `ROLE_PROMPTS`（各子代理角色）· `DECOMPOSE_SYSTEM`（任务拆解）
- 改动提示词 = 改 `core/prompts.py` 一处，随代码审查/提交（无热编辑）。
- 工具说明由 `@tool` schema 自动注入（现有机制）。

### 驾驭工程（Steering）
- 把用户**长期意图/偏好**（来自 Memory）在每次会话开头注入提示词，让行为稳定贴合用户习惯（如"默认中文、先确认再删除、操作报告要简洁"）。
- 通过 clarify 的**提问设计**引导任务不跑偏；critic 子代理做结果把关。

### 循环工程（Loop）
- `executor` 统一循环控制：**步数上限（`agent.recursion_limit`）/ 收敛判定（LLM 无 tool_calls 即 done）/
  ReAct 回喂格式**（工具结果按原顺序回喂 history）。
- 失败路径：工具异常转 `Error: ...` 字符串回喂 LLM 自行处理；重试/熔断/模型 failover 在
  `core/llm/client.py` 统一处理（可重试错误分类在传输层，非任务层）。当前**未实现**"参数错回 clarify"。
- 反思（reflect）：执行循环即 ReAct（观察工具结果后判断下一步），无独立反思步骤。

---

## 6. 安全与信任模型（无沙箱，人类在环）

用户明确不需要安全区，故不设强制沙箱；以「**人类在环确认 + 审计**」兜底风险：

| 操作类别 | 策略 |
|----------|------|
| 只读（查文件/搜索/查状态） | 自动执行 |
| 写/覆盖/删除/移动 | 默认先 confirm（基于工具实际风险，而非任务声明的 risk） |
| 执行任意 shell/py | 默认 confirm |
| 网络外发（上传/发消息） | 默认 confirm |
| 无人值守（定时任务） | 需确认的自动拒绝（`_SilentChannel`），被拒记 warning + 落盘历史 |

> 当前**未实现**信任记忆 / 黑名单白名单（每次高风险操作均需确认；无"信任该路径"持久化）。
所有工具执行与确认决策（含拒绝）写入 `data/audit.log`。

---

## 7. 技术选型与复用点（对接现有代码）

| 现有代码 | 复用方式 |
|----------|----------|
| `core/llm/stream.py` + `client.py` | 直接复用（SSE 解析/重试/熔断） |
| `core/tools/base.py` `@tool` 注册中心 | 扩展为统一工具入口（含 MCP 桥） |
| `core/config/` 包（pydantic 强类型 + 双文件密钥分离） | 分片：schema（模型）/ loader（YAML+密钥注入）/ runtime（单例+热重载） |
| `core/orchestrator/executor.py` ReAct 执行循环 | 简单任务走 ReAct；复杂任务转多智能体协调者 |
| `server.py` FastAPI + SPA | 宿主服务，新增 `/api/task`、`/api/env`、`/api/memory`、`/api/schedule` 等 |
| `web` Vue3 控制台（悬浮球 + /console） | 保留并新增任务/环境/记忆/定时视图 |
| `scripts/libs` 离线轮子 | 新增依赖（如 `pyautogui`、`openpyxl`、`vosk` 本地版）需补 wheel |

新增依赖（按需）：`vosk`（本地唤醒/ASR）、`piper`/`edge-tts`（本地 TTS）、`openpyxl`（xlsx）、`pyautogui`（GUI）、`duckduckgo-search`（已有）、MCP SDK。

---

## 8. 数据与状态设计

- **会话/历史** `data/history.db`：完整会话消息（控制台「历史」tab），`core/history.py::HistoryStore`。
- **任务** `data/tasks/<id>.json`：会话结束时由 `state.persist` 落盘（消息 + 任务结构化 + 状态）。
- **环境** `environment.md`（人可读，`core/detection/environment.py` 生成）。
- **记忆** `memory/facts.sqlite`（FTS5 trigram）。
- **定时** `data/schedules.json`。
- **审计** `data/audit.log`（工具执行与高风险确认决策）。

SSE 事件扩展：现有 `content_delta/tool_start/tool_end/usage/done/error` 之上新增 `task_state` / `question` / `confirm` / `stop_ack` / `schedule`。

---

## 9. 实施路线图（阶段化，每阶段可独立交付验证）

| 阶段 | 状态 | 内容 | 验收 |
|------|------|------|------|
| **P0 地基** | ✅ 已完成 | 环境感知→environment.md；execution（shell/py/fs）；tools 基础集；orchestrator（session/intent/task/clarify/confirm/executor/control）；SSE 事件扩展（语音监听详见「实现状态」：桌面监听暂停，浏览器 WASM 唤醒为当前入口） | 语音"把桌面 xx.txt 复制到下载" 全链路 + "停止"可中断 |
| **P1 记忆+RAG** | ✅ 已完成 | memory 两级（短期 + 长期事实 FTS5）；RAG 索引 environment.md 与文档目录；任务后事实提取 | 跨会话记住偏好；"按上次的方式查天气" 直接可用 |
| **P2 能力扩展** | ✅ 已完成 | MCP 客户端 + 桥；Skills 系统 | 接一个 MCP server 并语音调用其工具；语音"执行我 skill 里的 xxx" |
| **P3 多智能体+定时+GUI** | ✅ 已完成 | coordinator + 子代理（base.py 合一）；scheduler；gui 自动化 | 复杂任务自动拆解多步执行；"每天九点查天气并播报"；语音控制打开/操作应用 |

> 详细进度追踪见 `roadmap.md`。每阶段细化设计见 `docs/superpowers/specs/`，计划见 `docs/superpowers/plans/`。

---

## 附录 A：内置工具清单（26 个，`@tool` 注册中心实际注册）

| 类别 | 工具（风险） |
|------|-------------|
| 基础 | `grep_file`(read) `find_files`(read) `read_file`(read) `write_file`(write) `parse_doc`(read) `list_dir`(read) `stat_path`(read) `system_probe`(read) |
| 执行 | `run_shell_tool`(exec) `run_python_tool`(exec)（超时/流式/可 kill，独立子进程） |
| 检索 | `web_search`(read)（duckduckgo）`get_weather`(read)（wttr.in）`get_datetime`(read) `calculate`(read)（AST 白名单求值） |
| 记忆 | `memory_get`(read) `memory_put`(write) |
| 定时 | `register_schedule`(write) `list_schedules`(read) `remove_schedule`(write) |
| 技能 | `list_skills`(read) `run_skill_tool`(exec) |
| GUI | `gui_activate_tool`(read) `list_windows_tool`(read) `gui_click_tool`(exec) `gui_type_tool`(exec) `gui_screenshot_tool`(exec)（懒加载优雅降级） |
| MCP | 动态注册 `mcp_<server>_<tool>`（需配置 `mcp.servers`，`core/mcp/manager.py` 启动时注册） |

工具元信息（read/write/exec 风险级别）由 `@tool` 装饰器扩展出 `risk` 字段，供 confirm.py 判断；
risk 不进 LLM schema（避免部分 provider 拒绝未知字段）。
