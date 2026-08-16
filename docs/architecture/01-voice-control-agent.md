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
infinite-logic/
├── main.py                 # 入口：serve / install / probe
├── server.py               # FastAPI 宿主：/api/* + SSE + 静态面板
├── environment.md          # ★ 环境感知调查结果（独立 md，可随时更新）
├── core/
│   ├── config.py           # 配置（多 provider，复用现有）
│   ├── logger.py           # 日志 + 审计（复用现有 loguru）
│   ├── llm/                # LLM 客户端（复用现有 stream/client）
│   ├── voice/              # 语音层（当前：ASR/TTS）
│   │   ├── asr.py          #   语音转文字（在线/本地可选）
│   │   ├── tts.py          #   文字转语音（播报）
│   │   └── vad.py          #   端点/静音检测
│   ├── orchestrator/       # ★ 编排层（核心，全部自研）
│   │   ├── session.py      #   会话状态机与管理
│   │   ├── intent.py       #   意图判断：闲聊 or 任务
│   │   ├── task.py         #   任务形成：意图/参数/目标/缺失信息
│   │   ├── clarify.py      #   澄清循环：把缺失信息转问题，等操作者回答
│   │   ├── confirm.py      #   高影响操作复述确认
│   │   ├── executor.py     #   执行循环：plan → act → observe → reflect
│   │   └── control.py      #   ★ 停止/中止控制器（CancellationToken）
│   ├── agent/              # ★ 多智能体
│   │   ├── coordinator.py  #   协调者：拆解/分派/合并
│   │   ├── planner.py      #   规划子代理
│   │   ├── doer.py         #   执行子代理（调工具）
│   │   ├── searcher.py     #   检索子代理（RAG/网络）
│   │   └── critic.py       #   批评/自检子代理（收敛把关）
│   ├── tools/              # ★ 工具注册中心 + 基础工具（复用 @tool）
│   ├── mcp/                # ★ MCP 客户端（桥接外部能力）
│   ├── skills/             # ★ Skill 系统（能力包，热加载）
│   ├── rag/                # ★ 检索增强（索引/向量/检索注入）
│   ├── memory/             # ★ 记忆管理（短期/长期/向量，三级）
│   ├── scheduler/          # ★ 定时任务（cron 式）
│   └── execution/          # ★ 执行层
│       ├── shell.py        #   Shell 进程控制（超时/流式/可 kill）
│       ├── python.py       #   Python 脚本执行（独立进程）
│       ├── fs.py           #   文件系统（读写所有通用格式）
│       ├── envprobe.py     #   ★ 环境感知调查 → environment.md
│       └── gui.py          #   GUI 自动化（可选，pyautogui/win32）
├── prompts/                # ★ 提示词工程：所有系统提示集中管理（可热编辑）
│   ├── base.md             #   角色/能力/约束
│   ├── intent.md           #   意图判断
│   ├── task.md             #   任务形成/澄清提问
│   ├── executor.md         #   执行循环
│   └── agent_*.md          #   各子代理
├── skills/                 # Skill 定义文件
├── memory/                 # 长期记忆数据（sqlite/md）
├── data/                   # 运行时数据（会话/任务/trace）
└── web/                    # 控制台（复用现有，新增任务/记忆/环境/定时视图）
```

`★` = 本次新增/重构的重点模块。

---

## 3. 各层模块设计

### 3.1 交互层：语音 + 前端

**语音（当前实现：浏览器端）**——Vosk WASM 唤醒词在浏览器内运行，ASR/TTS 走后端 OpenAI 兼容接口：
- 浏览器端 `public/lib/vosk.js` + `wake-word.js`：离线唤醒词「小逻小逻」（含同音字变体），激活录音后经 ASR 转文字。
- ~~桌面常驻监听（本地 Vosk 后台常驻麦克风）~~：设计目标之一，**已暂停开发并移除**（代码在 `desktop-ball` 分支）；若未来恢复，可复用浏览器 WASM 方案作降级。
- `asr.py`：在线 OpenAI 兼容 ASR（现有）或本地 Whisper 二选一，配置切换。
- `tts.py`：播报回复/汇报（在线 TTS 或本地 piper）；浏览器端继续 SpeechSynthesis 作面板播报。
- 语音事件统一转成 `Utterance(text)` 推入编排层；**命令词**（"停止/取消/暂停"）在唤醒/ASR 层即时识别并直接触发 `StopController`，不经过 LLM（保证响应及时）。

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

**task.py（任务形成）**：LLM 结构化提取 `{goal, params, missing: [需要问操作者的信息], risk: low|medium|high}`。这是"先对话判断是否需要形成任务、需要问什么"的关键一步。

**clarify.py（澄清循环）**：把 `missing` 转成自然语言问题（"想对哪个文件操作？删除还是移动？"），通过语音/面板问操作者，**阻塞等待回答**；收到回答后回填参数，循环直到 `missing` 为空。每轮带最多提问次数上限，防止无限追问。

**confirm.py（确认层）**：`risk=high`（删除/覆盖/执行任意命令/网络外发/安装软件）时复述执行方案，请求明确确认；用户可说"确认"或"信任这类操作"（信任关系入 memory）。

**executor.py（执行循环）**：核心循环，即"循环工程"的实现载体：
```
plan（拆步骤）→ 每步：选工具/子代理 → act → observe（工具结果）→ reflect（是否达成目标）
收敛判定：目标达成 / 步数超限 / 连续失败 / 用户 stop
失败重试：区分可重试（网络/暂时）与不可重试（参数错→回澄清）
```

**control.py（停止/中止）★**：
- `CancellationToken` 贯穿 executor → 每个工具调用 → 每个子进程。
- 层级：`stop_task`（整个任务，递归 kill 子进程树）/ `stop_step`（当前步骤）/ `pause`（挂起等继续）。
- 触发源：命令词（语音）、面板按钮、定时器；LLM 主动请求。
- 兜底：OS 进程树 kill（Windows `taskkill /T`）。

### 3.3 智能体层：多智能体协作

- **coordinator.py**：把任务分解为子任务（LLM 结构化拆解），给每个子任务选子代理，汇总结果；子任务**相互独立**时可并发（asyncio.gather）。
- **子代理**（每个都是一次 LLM 循环，共享 Tools/RAG/Memory）：
  - `planner`：把目标转成有序步骤 + 前置条件。
  - `doer`：执行具体步骤，调工具，把结果回喂。
  - `searcher`：检索（RAG/网络/文件），供 doer 引用。
  - `critic`：对 doer 的结果自检（是否达到目标/有无副作用），可打回重做。
- **通信**：结构化消息 `{task_id, kind, payload, state}`，经协调者流转；任务状态写入 `data/tasks/<id>.json`，前端可实时 SSE 展示。

### 3.4 能力层

**Tools（基础工具，够底层）**：复用现有 `@tool` 注册中心（`core/tools/base.py`）。基础集见 §附录A。工具分三类：只读（自动执行）、写（需 confirm 策略）、执行（需 confirm 策略）。

**MCP**：`mcp/client.py` 连接外部 MCP server（filesystem/git/browser/数据库/浏览器控制等），把 MCP 工具动态注册进 `TOOLS`（`tools/mcp_bridge.py`），对编排层透明。

**Skills（能力包）**：`skills/*.yaml` 定义：`name / description / requires / steps(模板) / validate / dangerous`。执行时 Skill 展开为一串工具步骤模板，由 doer 填充参数。热加载（`skills/loader.py` 监听目录）。

**RAG**：索引源 = environment.md、用户文档目录、代码库、（可选）历史对话。`rag/indexer.py` 建索引（起步用 sqlite + 简单 TF-IDF/关键词，可选升级向量库），`rag/retriever.py` 检索 top-k 片段注入上下文。

**Memory（三级）**：
| 级 | 存什么 | 存哪 | 何时写 |
|----|--------|------|--------|
| 短期 | 当前会话消息/工具结果 | 内存 session | 实时 |
| 长期·事实 | 用户偏好、常用路径、信任关系、环境结论 | `memory/facts.sqlite` + md | 任务结束后 LLM 摘要提取 |
| 长期·向量 | 历史对话/重要结论 | `memory/vectors` | 任务结束后异步 |

读取：执行前把相关事实（按当前任务主题检索）注入系统提示；"记忆管理"模块负责读写隔离与去重。

**Scheduler（定时任务）**：cron 式注册（`data/schedules.json`，可语音注册"每天九点查天气"）。后台循环到点触发 → 构造 `Task` 推入编排层 → 结果播报/写入历史。支持一次性提醒与周期任务。

### 3.5 执行层

- **shell.py**：`subprocess` 封装——超时、流式 stdout 捕获、**可中止**（kill 进程树）、cwd/环境变量控制。是"Shell 控制"的基础。
- **python.py**：执行 .py 脚本（独立子进程，避免污染宿主；`sys.executable` 隔离）。
- **fs.py**：读写**所有通用格式**：text / json / yaml / toml / md / csv / xlsx / sqlite / ini / env；每个格式一个 reader/writer 分发器；写前快照（可选）支持回滚。
- **envprobe.py（环境感知）★**：见 §4.1。
- **gui.py（可选）**：pyautogui/win32——鼠标点击/键盘输入/窗口激活/截图，实现"控制 GUI 应用"。

---

## 4. 核心流程

### 4.1 环境感知调查（安装时 + 随时更新）

```
安装/首次运行 → envprobe.py 全量调查：
  OS 版本/架构/主机名 · CPU/内存/磁盘 · 已装软件与常用命令
  网络与代理 · PATH/默认 Shell · 桌面/文档/下载路径
  浏览器/编辑器/Python 版本 · 可用的 LLM/ASR/TTS provider
→ 结构化 + 自然语言写入 environment.md（独立文件，前端/执行层/RAG 都读它）
可随时触发：语音"更新环境信息" / 面板按钮 / 任务前按需 → 重新 probe 并合并增量到 environment.md
```

agent 每次规划时把 `environment.md`（或其相关段）注入上下文，让工具参数（路径、命令）贴合真实系统。

### 4.2 语音 → 任务 → 执行 → 汇报 闭环

```
1. 唤醒 → ASR → 文本
2. intent.py：闲聊 or 任务？
    闲聊 → LLM 回复 → TTS 播报（不进入任务）
3. task.py：形成任务 {goal, params, missing, risk}
4. clarify.py：把 missing 作为问题问操作者，等回答，循环到信息足够（上限 N 轮）
5. confirm.py：risk=high 先复述方案，确认后执行
6. coordinator + executor：拆子任务 → 子代理 → 工具 → 回喂 → 收敛
7. reporting：TTS 播报结果摘要；面板 SSE 展示完整执行流
任何时刻："停止/取消/暂停" → control.py 立即中止
```

### 4.3 停止 / 中止机制

- **令牌贯穿**：`CancellationToken` 从会话 → 任务 → 工具 → 子进程；每个 await 点检查 `is_cancelled`。
- **层级**：`stop_task`（含 kill 进程树）/ `stop_step` / `pause`。
- **状态记录**：任务标记 `stopped/paused`，后续可"继续/重跑"，不丢上下文。
- **兜底**：执行层 kill 不了时 OS 级强杀；审计记录谁在何时中止了什么。

---

## 5. 工程方法论：提示词 / 驾驭 / 循环

### 提示词工程
- 所有系统提示集中在 `prompts/`，**热编辑生效**（下次任务读取新文件）。
- 分层：`base`（角色/能力/约束/工具说明）→ `intent` → `task` → `executor` → `agent_*`。
- 工具说明由 `@tool` schema 自动注入（现有机制）。

### 驾驭工程（Steering）
- 把用户**长期意图/偏好**（来自 Memory）在每次会话开头注入提示词，让行为稳定贴合用户习惯（如"默认中文、先确认再删除、操作报告要简洁"）。
- 通过 clarify 的**提问设计**引导任务不跑偏；critic 子代理做结果把关。

### 循环工程（Loop）
- `executor` 统一循环控制：**步数上限 / 收敛判定 / 可重试错误分类 / ReAct 回喂格式**。
- 失败路径：参数错 → 回 clarify；工具临时失败 → 重试；连续失败 → 停并报告。
- 反思（reflect）：每步结束让 LLM 判断"目标是否达成/下一步"，避免空转。

---

## 6. 安全与信任模型（无沙箱，人类在环）

用户明确不需要安全区，故不设强制沙箱；以「**人类在环确认 + 审计**」兜底风险：

| 操作类别 | 策略 |
|----------|------|
| 只读（查文件/搜索/查状态） | 自动执行 |
| 写/覆盖/删除/移动 | 默认先 confirm；用户可说"信任该路径/该类操作"（记入 memory） |
| 执行任意 shell/py/安装软件 | 默认 confirm；一次性信任或长期信任可配置 |
| 网络外发（上传/发消息） | 默认 confirm |
| 高危白名单（如 `rm -rf /` 级） | 可选黑名单保险（非强制，用户可关） |

所有操作（尤其是被确认与被执行的高影响操作）写入 `data/audit.log`。前端面板可查看信任关系并随时撤销。

---

## 7. 技术选型与复用点（对接现有代码）

| 现有代码 | 复用方式 |
|----------|----------|
| `core/llm/stream.py` + `client.py` | 直接复用（SSE 解析/重试/熔断） |
| `core/tools/base.py` `@tool` 注册中心 | 扩展为统一工具入口（含 MCP 桥） |
| `core/config.py` 多 provider | 扩展新增 voice/mcp/rag/memory 配置段 |
| `core/agent.py` ReAct | 演进为 `executor.py` 执行循环 |
| `server.py` FastAPI + SPA | 宿主服务，新增 `/api/task`、`/api/env`、`/api/memory`、`/api/schedule` 等 |
| `web` Vue3 控制台（悬浮球 + /console） | 保留并新增任务/环境/记忆/定时视图 |
| `scripts/libs` 离线轮子 | 新增依赖（如 `pyautogui`、`openpyxl`、`vosk` 本地版）需补 wheel |

新增依赖（按需）：`vosk`（本地唤醒/ASR）、`piper`/`edge-tts`（本地 TTS）、`openpyxl`（xlsx）、`pyautogui`（GUI）、`duckduckgo-search`（已有）、MCP SDK。

---

## 8. 数据与状态设计

- **会话** `data/sessions/<id>.json`：消息、状态机、归属任务。
- **任务** `data/tasks/<id>.json`：目标/参数/计划/步骤结果/状态（queued→planning→running→waiting_question→waiting_confirm→done|failed|stopped|paused）。
- **环境** `environment.md`（人可读）+ `data/env_cache.json`（程序用）。
- **记忆** `memory/facts.sqlite` + `memory/vectors` + `memory/notes/`（md）。
- **定时** `data/schedules.json`。
- **审计** `data/audit.log`。

SSE 事件扩展：现有 `content_delta/tool_start/tool_end/usage/done/error` 之上新增 `task_state` / `question` / `confirm` / `stop_ack` / `schedule`。

---

## 9. 实施路线图（阶段化，每阶段可独立交付验证）

| 阶段 | 内容 | 验收 |
|------|------|------|
| **P0 地基** | envprobe→environment.md；execution（shell/py/fs）；tools 基础集；orchestrator（session/intent/task/clarify/confirm/executor/control）；SSE 事件扩展（语音监听详见「实现状态」：桌面监听暂停，浏览器 WASM 唤醒为当前入口） | 语音"把桌面 xx.txt 复制到下载" 全链路 + "停止"可中断 |
| **P1 记忆+RAG** | memory 三级；RAG 索引 environment.md 与文档目录；任务后事实提取 | 跨会话记住偏好；"按上次的方式查天气" 直接可用 |
| **P2 能力扩展** | MCP 客户端 + 桥；Skills 系统 | 接一个 MCP server 并语音调用其工具；语音"执行我 skill 里的 xxx" |
| **P3 多智能体+定时+GUI** | coordinator + 子代理；scheduler；gui 自动化 | 复杂任务自动拆解多步执行；"每天九点查天气并播报"；语音控制打开/操作应用 |

> 每阶段开始前，先在 `docs/architecture/` 追加该阶段的细化设计（模块接口/数据流/测试），再按 superpowers 计划流程实施。

---

## 附录 A：基础工具清单（够底层、可组合）

| 工具 | 说明 |
|------|------|
| `grep_file` / `find_files` | 按内容/文件名搜索（rg 语义） |
| `read_file` / `write_file` / `append_file` | 文本/二进制读写 |
| `parse_doc` | 读 json/yaml/toml/md/csv/xlsx/sqlite/ini 等通用格式 |
| `list_dir` / `stat_path` | 目录/文件元数据 |
| `copy_move_delete` | 文件操作（高影响走 confirm） |
| `run_shell` | 执行命令（超时/流式/可 kill） |
| `run_python` | 执行 .py（独立进程） |
| `web_search` | 网络搜索 |
| `http_get` / `http_post` | 抓网页/调 API |
| `system_probe` | 实时读系统状态（复用 environment.md + 实时命令） |
| `get_datetime` / `calculate` | 现有工具保留 |
| `list_processes` / `kill_process` | 进程管理 |
| `set_reminder` / `register_schedule` | 定时任务入口 |
| `memory_get` / `memory_put` | 长期记忆读写 |
| `env_update` | 触发环境感知增量更新 |
| `gui_click` / `gui_type` / `gui_activate`（可选） | GUI 自动化 |

工具元信息（读/写/执行风险级别）由 `@tool` 装饰器扩展出 `risk` 字段，供 confirm.py 判断。
