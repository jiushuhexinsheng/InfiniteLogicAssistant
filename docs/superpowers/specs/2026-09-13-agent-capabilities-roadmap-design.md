# Agent 能力扩展路线图（P4–P8）— 分解设计

日期：2026-09-13
状态：待审批
类型：**分解文档**（不是单一子系统的设计；每个子系统另出 spec）

## 为什么先写这份文档

原始需求是 6 条（用户编号 1、2、3、4、6、7，第 5 条用户确认不存在），经勘察确认它们是 **5 个相互独立的子系统**，而不是一件事。按 superpowers 流程，多子系统需求必须先分解、定接口边界与顺序，再逐个走 spec → plan → 实施。

本文档的产出：需求到子系统的映射、现状勘察基线（带行号，避免后续设计凭空猜测）、每个子系统的接口边界与待决问题、以及推进顺序。

## 需求 → 子系统映射

| 子系统 | 主题 | 对应需求 | 依赖 |
|---|---|---|---|
| **A** | 工具权限策略层（allow / ask / deny，规则 > 例外 > 默认） | 1 | 独立 |
| **B** | 询问类型扩展（choice / text / composite） | 2 | — |
| **C** | 语音作答 + 无应答待机 + 再唤醒续答 | 3、4 | **B** |
| **D** | 问答进聊天记录与历史 | 6 | B |
| **E** | 任务知识库（完成确认 + 成功任务存档 + 相似任务复用） | 7 | A、B、D |

**建议顺序：B + D → A → C → E。** B 是 C 与 E 的共同地基；A 完全独立、可与 B 并行；C、E 各自建在前序成果上。

## 勘察基线（已验证事实）

以下为本次勘察确认的现状，后续设计以此为准，不得凭印象假设。

### 前端语音通路

- `useWakeWord.ts` **没有独立状态机**，直接写 `store.state`；`AsstState` 9 值定义在 `store.ts:6-15`。
- 录音运行时变量是模块级 `let`（`useWakeWord.ts:7-11`），**不在 store、跨组件不可观测**。
- **语音回答提问完全不存在，且会破坏当前提问**：
  - `handleTranscript`（`useWakeWord.ts:240-258`）**无 `pendingQuestion` 分支**，转写文本一律 `addMessage('user')` + `runTurn()` → 开新一轮 `/voice/utter`。
  - 后端每次 utter 都新建 `Session()` + `run_pipeline`（`core/api/voice.py:155-186`），**不检测该会话是否正阻塞在 `ask()`**；前端 `runTurn` 会 `abortController.abort()` 掐掉上一条流（`useChat.ts:30`），**旧 `ask()` 永久挂死**。
  - `sendAnswer`（`useChat.ts:152` → `/voice/answer`）只被 `QuestionCard.vue:48,59` 与 `ConsoleTaskView` 触达，语音路径从不触达。
- **播报与监听无互斥**：`speakAuto` 调用点 `useChat.ts:116,124-126,142`；无暂停接口，wake-word 引擎麦克风全程开启（`public/lib/wake-word.js:146-148` 仅 getStream/isRunning/isModelLoaded），仅 `getUserMedia` 开了 `echoCancellation`（`:97`）。**助手自己的播报可能自触发唤醒**。

### 后端存储（四套独立，无外键）

| 存储 | 位置 | 结构 | 对本需求的适配性 |
|---|---|---|---|
| 事实记忆 | `memory/facts.sqlite` | `facts(id,topic,content,source,ts)` + FTS5 **trigram** | `upsert` 是**覆盖式**、topic 语义，无版本历史 → **不适合存只增不改的任务记录** |
| RAG 索引 | `rag/index.db` | `chunks(path,section,text)` + `chunk_terms`，BM25 | 每次 `index_sources()` **全量 DELETE 重建**（`indexer.py:78-79`），源为 `environment.md` + `docs/` → **不能存运行时记录** |
| 会话历史 | `data/history.db` | `conversations` + `messages` | 会话形状；`save_conversation` 整段覆盖 |
| 任务落盘 | `data/tasks/<session_id>.json` | 单会话一个文件 | **无索引**；`persist` 只留末 20 条消息且**剥掉 `tool_calls`**（`api/state.py:117-120`） |

### 编排与工具

- `Task`（`task.py:39-51`）：`id, goal, params, missing, risk, state` —— **无时间戳字段**。
- `extract_and_store`（`extract.py:38`）：仅 `done/failed` 时执行；LLM 自由生成 topic/content，**无 param/step 结构**；写 `source=f"task:{task.id}"`；异常静默。
- 澄清循环 `run_clarify`（`clarify.py:15`）：`missing[0]` 逐条问，`MAX_CLARIFY_ROUNDS=3`，每轮重 `form_task` 合并 params。
  - **可插钩子点**：`pipeline.py:170-172`（`if task.missing:` 之后、`run_clarify` 之前）最自然 —— 可先检索历史成功任务预填 `task.params`；或在 `clarify.py:28-31` 循环前预填 `answered`/`params`。
- `TOOLS.risk(name)`（`base.py:56-66`）：**未知工具返回 `"read"`** —— 这是 **fail-open**。消费点：`confirm.py:102`、`executor.py:143-144`、`api/tools.py`。**无任何「工具→策略」配置入口**，risk 是装饰器硬编码静态值。
- 新增 Settings Section 需改：`schema.py` → `core/config/__init__.py` → `runtime.py:200-239 editable_snapshot()` → `detection/validator.py` → 前端 `configDefs.ts`(`advancedDefs:61-72`/`NUMERIC:75`/`LABELS:83`) 与 `ConsoleSettings.vue menuDefs:42-48` → `config.yaml` + `config.yaml.example`。`api/settings.py` 的通用 PATCH **无需改**。

## 参照实现的可用机制（openclaw / DSH）

| 机制 | 来源 | 本项目采纳方式 |
|---|---|---|
| 三桶策略 `allow / deny / ask` | OpenClaw 权限插件 | A 的策略动作集 |
| 优先级 `规则 > 例外 > 默认` | `dsh-permgate` | A 的求值顺序 |
| `allow-once` / `allow-always` | OpenClaw 审批决策 | A 的「本次放行 / 永久放行」 |
| **危险模式永不允许持久化为 allow-always** | OpenClaw | A 的不可持久化黑名单 |
| **deny 单调、不可被后续规则翻案** | `dsh-path-guard` | A 的求值短路 |
| 无审批通道时 `ask` 即 `deny` | DSH 原生 | **本项目已实现**（`confirm.py:70-72`） |
| 分层：确定性规则 → 模型审查 → 人工 | `dsh-tiered-approval` | A 的可选扩展，本期不做 |

---

## 子系统 A：工具权限策略层

**目标**：把硬编码的 `risk → 是否询问` 换成可在设置里配置的策略，让常用只读/低危工具默认免询问。

**接口边界**
- 新增 `core/tools/policy.py`：`decide(name, args) -> Decision(action: allow|ask|deny, rule: str)`
- 新增配置段 `permissions`（Settings Section），结构形如 `{default: "ask", rules: [{match: "read_*", action: "allow"}], exceptions: [...], persist_denied: ["run_shell_tool", "run_python_tool"]}`
- 消费点替换：`confirm.py` 的 `confirm_tool` 改为询问 `policy.decide()`；`executor.py:143-144` 的 read 并发/串行分组也改由 policy 决定
- 前端：设置页新增「权限」菜单项

**关键决策（需在 A 的 spec 阶段定）**
1. **必须修 `TOOLS.risk()` 的 fail-open**：策略层的未知工具名必须按**最严格**处理（`ask` 或 `deny`），不能沿用 `"read"`。同时 `validator.py` 校验策略里引用的工具名存在于 `TOOLS.has()`。
2. 匹配维度：按**工具名 glob** 还是按**类别**（dsh-permgate 的六大类）？前者简单，后者更贴人意。
3. `allow-always` 的落点：写配置（持久）还是会话内（临时）？危险工具不可持久化，名单怎么定。
4. 策略求值失败（配置损坏）时的默认动作 —— 必须 fail-closed。

**风险**：策略放宽即降低安全边界。README 目前明确写「无沙箱 + 人类在环」，A 实施后需同步修订该表述，避免文档承诺与实现不符。

**spec 大纲**：策略数据结构与求值算法 / 与 `TOOLS.risk()` 的关系（替代还是叠加）/ 设置页交互 / 审计格式 / 迁移（现有 `risk` 装饰器是否保留）。

---

## 子系统 B：询问类型扩展

**目标**：询问支持三类 —— **选择**（按钮）、**文本**（自由输入）、**综合**（选择 + 文本并存）。

**现状**：上一轮刚做完结构化确认，`QuestionEvent.kind` 现为 `clarify | confirm` 二值（`core/orchestrator/events.py:87-102`）；前端 `QuestionCard.vue`、`ConsoleTaskView.vue` 各按 `kind` 分流渲染。

**接口边界**
- `QuestionEvent` 扩展：`kind` 枚举化，并为选择类携带 `options: [{value,label}]`、为综合类携带 `allow_text: bool`
- `Answer`（`session.py`）已具备 `text` + `choice` 两字段，**天然支持综合类**，无需改结构
- 前端 `QuestionCard.vue` 的 `isConfirm` 分支泛化为按 `kind` 渲染三态

**关键决策**
1. `kind` 的取值集合：把现有 `confirm` 保留为 `choice` 的**特例**（固定两选项 yes/no），还是完全替换？保留兼容可减少改动面，但两套语义并存易混淆。
2. 综合类的语义：用户**必须**两者都给，还是**任选其一**？前者更严格、后者更顺。建议任选其一（`Answer` 结构已支持）。
3. 谁来决定询问类型 —— LLM 在 `form_task` 时判定（需扩 tool schema），还是编排层按场景硬编码？建议 LLM 判定 + 编排层兜底，与现有 `judge_intent`/`form_task` 风格一致。

**spec 大纲**：`kind` 取值与兼容策略 / options 的来源 / 三态渲染 / 与 `/api/voice/answer` 的契约 / 测试矩阵。

---

## 子系统 C：语音作答 + 无应答待机 + 再唤醒续答

**目标**（需求 3、4）：提问时自动进入语音监听，操作者可用语音回答（语音为主、文本为辅）；无应答则进入待机；再次唤醒时回到**本次未答完的提问**。

**现状风险（必须先修，否则功能不可用）**
- 见「勘察基线」：语言通路不认识 `pendingQuestion`，一说话就开新一轮并**掐死挂起的 `ask()`**。C 的第一步必须是**让语音通路认识「正在等回答」**。
- 播报与监听无互斥，助手自己播报的内容可能自触发唤醒。

**接口边界**
- `useWakeWord.ts` 引入**显式状态机**（当前是散落的 `state.value = ...` 赋值），至少区分：`idle / listening / recording / transcribing / awaiting_answer / standby`
- `handleTranscript` 增加分流：`pendingQuestion` 非空 → 走答案通道（`sendAnswer`），否则走 `runTurn`（现状）
- 后端 `/api/voice/utter` 需能识别「该 session 正阻塞在 `ask()`」，避免新一轮覆盖；或前端在 `pendingQuestion` 非空时**不发 utter**
- 待机/恢复：需要一个「未应答超时 → standby」的计时器（可参考现有 `startMaxTimer` `useWakeWord.ts:177-182`），以及「再唤醒 → 回到 pendingQuestion」的恢复路径
- TTS 播报期间**门控麦克风**（`speakAuto` 前后暂停/恢复唤醒引擎）

**关键决策（需在 C 的 spec 阶段定）**
1. **待机的语义**：引擎完全停止（省电、需重新加载模型）还是继续监听但不录音？后者体验好、前者省资源。
2. 超时时长：多久没回答算「无应答」？可配还是固定？
3. 续答的生命周期：任务侧 `ask()` 一直阻塞着 —— 待机期间后端会话如何保活/超时？（现有 `SESSION_TTL=30min`，`api/state.py:17`）
4. 语音作答是否也支持**综合类**（先说选项、再说补充）？还是语音只走选择/短文本，综合类强制用 UI？

**风险**：这是 5 个子系统里最重的一块 —— 涉及前端状态机重构 + 后端会话保活 + 音频互斥三处，且**只能通过真实麦克风/扬声器验证**（自动化测试覆盖有限，需明确人工验证清单）。

**spec 大纲**：状态机定义与迁移表 / 待机与恢复时序 / 麦克风门控 / 后端会话保活 / 人工验证脚本。

---

## 子系统 D：问答进聊天记录与历史

**目标**（需求 6）：提问与回答都出现在聊天记录里。

**现状**：`ChatMessage {id, role: 'user'|'assistant'|'system', text, toolCalls?, timestamp}`（`store.ts:36-47`）；`addMessage(role, text, toolCalls?)`。目前提问/回答**不进 messages**，只以悬浮卡片形式存在。

**接口边界**
- 提问时 `addMessage('assistant', 问题文本)`；回答时 `addMessage('user', 回答文本)`
- 选择类回答的文本形式（如「确认执行」/「取消执行」）已在 `ConsoleTaskView.choose()` 中有先例
- 会话落盘链路已通：`persist()` → `save_conversation()`（`api/state.py:101-136`）

**关键决策**
1. 是否需要区分「普通消息」与「问答消息」的视觉样式？若要，`ChatMessage` 需加 `kind` 字段（会波及 `buildHistory`、`ConsoleMessageList`、`persist`）。
2. 问答是否要进 `buildHistory()` 送给 LLM 做多轮上下文？（进了会让模型看到自己问过什么，通常有益）

**规模**：这是 5 个子系统里最小的一个，适合与 B 合并为同一轮 spec。

---

## 子系统 E：任务知识库

**目标**（需求 7）：任务完成后询问「是否完成」；把**成功**的任务存入独立模块；今后执行相同/相似任务时作为参考，**减少询问**。

**接口边界**
- **新增独立存储**：建议 `memory/tasks.sqlite`，沿用 `facts.py` 已验证的 **FTS5 trigram** 模式，但表结构面向任务：
  `tasks(id, goal, params_json, steps_json, status, created, source_session)`
  —— 不复用 `facts.sqlite`（覆盖式、topic 语义、无 param/step 结构），也不复用 `rag/index.db`（全量重建）。
- 新增 `core/tasks/` 模块：`record(task, result)` / `find_similar(goal, top_k)` 
- **完成确认**：编排层在 `execute_task` 返回 `done` 后、汇报前插入一次询问（复用 A/B 的询问机制）
- **减少询问**：钩子点在 `pipeline.py:170-172`（`run_clarify` 之前）—— 先 `find_similar(goal)`，命中则以历史 `params` 预填 `task.params`，使 `missing` 中的已知项不再提问
- `Task` 需加时间戳字段（现在没有）

**关键决策**
1. **完成确认与减少询问的关系 —— 已裁决（2026-09-13）**：两者不冲突，按**模式**区分：
   - **任务模式**：**要询问**（完成确认走询问）
   - **正常模式**：**减少询问**（复用历史、少打断）
   - ⚠️ **待澄清**：「任务模式 / 正常模式」的**判定依据**尚未定义（是用户在 UI 显式切换？还是按任务复杂度自动判定？还是按「控制台任务 tab vs 悬浮助手」区分？）。此项**必须在 E 的 spec 阶段先行确认**，它决定「完成确认」是否出现，进而决定 E 的整体交互。在确认前不得假设任何一种。
2. **相似度**：FTS5 trigram 匹配 `goal` 是否够用？还是需要向量检索（会引入新的依赖与存储）？建议先用 FTS5 + 关键词，跑一段看效果再决定（YAGNI）。
3. 存什么：只存 `goal + params`（用于减少询问），还是连 `steps` 一起存（可用于回放/复用执行路径）？后者野心大得多。
4. 复用时的**安全**：历史任务可能是 `exec` 风险，预填参数不等于免确认 —— A 的策略必须仍然生效。

**风险**：E 是唯一会**改变现有澄清行为**的子系统，实施后「同一个任务第二次执行会问得更少」，需明确当历史记录**过时或错误**时的纠正路径（否则错误参数会被反复预填）。

**spec 大纲**：存储结构与索引 / 完成确认的时机与频率 / 相似检索与预填算法 / 过时记录的处理 / 与 A 策略的交互。

---

## 横切关注点

1. **`TOOLS.risk()` 的 fail-open 是 A 的前置缺陷**：未知工具名返回 `"read"`（放行）。A 必须同时修掉，否则策略层建立在一个会静默放行的地基上。
2. **四套存储 + E 的第五套**：本路线图不打算合并它们（那是独立的重构议题），但 E 新增存储时**必须**在文档中写明与其余四套的关系与 ID 语义，避免第六套出现时无人能说清。
3. **询问机制是 B/C/D/E 的共同依赖**：B 定的 `kind` 与 `Answer` 契约会被 C（语音作答）、D（入记录）、E（完成确认）同时消费。**B 的 spec 应优先并冻结接口**。
4. **文档同步**：A 落地后 README 的「无沙箱 + 人类在环」表述、`docs/architecture/roadmap.md` 的阶段表都需更新。

## 推进方式

每个子系统独立走一轮完整流程，互不合并（B 与 D 例外，建议同轮）：

```
子系统 spec（brainstorming → docs/superpowers/specs/）
  → 用户审 spec
  → writing-plans → docs/superpowers/plans/
  → TDD 实施（每 Task 独立测试 + 独立 commit）
  → 验证（pytest + mypy + npm test + build + 真实 UI/语音人工验证）
```

并在 `docs/architecture/roadmap.md` 增加 P4–P8 行，与既有 P0–P3 表格式一致。

## 本轮不做（明确排除）

- 合并现有四套存储（独立议题）
- 向量检索 / embedding（E 先做 FTS5，看效果再说）
- `dsh-tiered-approval` 式的 LLM 审查层（A 的可选扩展，本期只做确定性规则）
- 沙箱 / 文件系统范围控制（A 只管「是否询问」，不管「能否执行」—— 沿用现有无沙箱前提）
