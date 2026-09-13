# 语音作答 + 无应答待机 + 再唤醒续答 设计文档（P6 / 子系统 C）

日期：2026-09-13
状态：待实施
上游：[Agent 能力扩展路线图](2026-09-13-agent-capabilities-roadmap-design.md) 的子系统 C

## 背景

需求原文：
> 3. 询问时要调用语音唤醒让操作人员语音回答；操作人员没有回答则进入待机；再次唤醒时进入本次回答
> 4. 回答可以是输入回答也可以是语音回答，以语音回答为重点

现状勘察出**三处真实问题**（均已定位到行号）：

| # | 问题 | 位置 | 后果 |
|---|---|---|---|
| 1 | `handleTranscript` **无 `pendingQuestion` 分支**，转写一律 `addMessage('user')` + `runTurn()` 开新一轮 `/voice/utter` | `useWakeWord.ts:240-258` | 用户在提问待答时一开口，**当前提问被搞挂** |
| 2 | 每次 utter 都新建 `Session` + `run_pipeline`，**不检测该会话是否正阻塞在 `ask()`**；前端 `runTurn` 又 `abortController.abort()` | `core/api/voice.py:155-186`、`useChat.ts:30` | **旧的 `ask()` 永久挂死**（等不到回答） |
| 3 | **播报与监听无互斥**：引擎无 pause/mute，`_muteGain` 只是「不回放麦克风」不阻止识别 | `useChat.ts:116,124-126,142`、`public/lib/wake-word.js:146-148` | 助手自己的播报（若含「小逻小逻」）**自触发唤醒** |

因此本设计不只是「加一条语音通路」，而是**先让语音通路认识「正在等回答」这个状态**，否则功能一上线就会破坏现有提问流程。

## 已确认决策

| # | 决策 | 说明 |
|---|---|---|
| 1 | **提问播报结束自动开录音** | 用户直接开口即答，不必再说唤醒词；VAD 静音超时 → 待机；待机时唤醒词仍生效，再唤醒回到**本题** |
| 2 | **播报期间暂停监听** | `speakAuto` 前 `WakeWordEngine.stop()`、播完 `start()`。已确认 **不重载模型**（只重建麦克风流与 recognizer） |
| 3 | **语音可精确匹配 option 的 label** | ASR 文本与 `options[].label` **trim 后精确相等**则回传对应 `value`；不命中则当文本 |

> **决策 3 的安全边界**：只做 **trim 后精确相等**，绝不做子串/模糊匹配。这与确认层 `_resolve_confirm` 的精确同义词表同一原则 —— 上一轮刚为「自由文本→批准判定」做过专项整改，本设计**不重新引入模糊解析**。ASR 多空格、错字、标点差异 → 不命中 → 保守当作文本。

> ⚠️ **后续变更（2026-09-13 当晚，本决策的前半部分已被取代）**：端到端实测暴露了上面这条原则
> 与语音通道的矛盾 —— 把界面按钮上的「允许本次」**原样念出来**也会被确认层拒绝（同义词表里
> 没有这个 label），任何自然表达都进不了批准。于是确认层的 `_resolve_confirm` 之后**新增了
> LLM 兜底层**：确定性层（结构化选择 + 精确字面量）保持不变且优先，判不了才交 LLM；LLM 只收到
> 用户那一句、输出限闭集三态、除明确 approve 外一律拒绝。**`matchOption` 未改**（仍是精确匹配）。
> 详见 `core/orchestrator/confirm.py` 模块 docstring。

## 状态机设计

`AsstState`（`store.ts:6-15`）新增两个值，把「等待回答」与「待机」从既有的 `recording` / `listening` 中区分出来：

```
提问播报完（onQuestion + TTS 结束）
   ↓ 自动开录
awaiting_answer   转写将走答案通道（sendAnswer）
   ↓ VAD 静音超时（answer_timeout_s，默认 8s）无人说话
standby           引擎仍在听唤醒词，但不录音
   ↓ 说「小逻小逻」命中
awaiting_answer   回到本题，不开新一轮
   ↓ 转写成功
thinking → …      正常流程（或再次提问则回到 awaiting_answer）
```

**与既有状态的差异**：
- `recording` 是「用户说完唤醒词后录音」；`awaiting_answer` 是「系统在等某个提问的答案」——两者的转写去向不同（后者走答案通道）
- `listening` 是「等待唤醒词，唤醒后开新一轮」；`standby` 是「等待唤醒词，唤醒后**续答本题**」

**`useWakeWord.ts` 引入显式迁移表**：当前是无独立状态机、散落地直接写 `store.state`。本设计把它收敛为一个集中的迁移函数，使「谁能从哪个状态去哪」可读可测。

### 波及面（新增状态值的同步点）

| 位置 | 需同步 |
|---|---|
| `store.ts:6-15` | `AsstState` 联合类型 |
| `MiniPlayer.vue:65` | `ACTIVE_STATES` 数组（`awaiting_answer` 属活跃；`standby` 不属） |
| `MiniPlayer.vue:82` | `['recording','listening']` 判定（`awaiting_answer` 应算作「可打断」） |
| `MiniHistory.vue:6,11,12` | 状态文案（补「请说…」/「待机中」） |
| `FloatBall.vue:203,211` | `recording` 的进度视觉（`awaiting_answer` 应同样显示） |
| `useAssistantVisuals.ts` | 状态→视觉映射 |

## 语音作答路由（核心修复）

`handleTranscript` 改为：

```ts
// 提问待答时：转写走答案通道，绝不开新一轮
if (pendingQuestion.value) {
  const matched = matchOption(text, pendingQuestion.value.options)
  await sendAnswer(matched ? '' : text, matched?.value)
  return
}
// 否则维持原行为
addMessage('user', text)
await runTurn()
```

`matchOption(text, options)` —— 纯函数，放 `composables/assistant/answerMatch.ts`：

```ts
/**
 * 把转写文本匹配到某个选项：仅 trim 后精确相等。
 * 不做子串/模糊匹配 —— 与确认层的精确同义词表同一原则，
 * 避免「不要执行」这类否定表达被误判为批准。
 */
export function matchOption(text: string, options: QuestionOption[]): QuestionOption | null
```

匹配规则：`text.trim() === option.label.trim()`。**不做**大小写归一、全角半角转换、标点剥离 —— 任何归一化都是模糊匹配的入口。

## 音频互斥

### 必要前置改动：`speakText` 需要播报完成信号

`speakText`（`useTts.ts:161`）目前**同步返回 void**，没有完成回调；而门控必须覆盖**整个播报时长**。两条路径都有天然钩子但未被使用：

- `speakBrowser`（`:117`）：`SpeechSynthesisUtterance` 的 `u.onend` / `u.onerror`
- `speakApi`（`:137`）：`audio.onended` / `audio.onerror`（当前只做 `revokeObjectURL`）

改动：`useTts` 暴露 `speaking = ref(false)`，在上述四个钩子里置位/复位。

**并发陷阱**：`speakBrowser` 会先 `speechSynthesis.cancel()`，上一个 utterance 的 `onend` 可能迟到并把 `speaking` 提前置 false。处置：用**代际计数**（每次播报 `++gen`，回调里仅在 `gen` 未变时复位）。

### 门控

`useWakeWord` 里 `watch(speaking)`：

```
speaking 变 true  → 若引擎运行中：stop()（释放麦克风轨道）
speaking 变 false → 若处于 listening/standby/awaiting_answer：start()
```

**注意**：`stop()` 释放麦克风轨道后，`awaiting_answer` 的录音也会一并中断。故播报结束后的 `start()` 需要按当前状态恢复：若播放前在 `awaiting_answer`，播完应重新进入 `awaiting_answer` 并开始录音。

## 后端防御（纵深）

`/voice/utter` 若带 `session_id` 且该会话**正阻塞在 `ask()`**，返回明确错误（400）而不是新建 Session 覆盖注册表、把旧的 `ask()` 变成孤儿。

实现：`EventQueueChannel` 增一个 `awaiting_answer: bool` 标志，`ask()` 进入时置 true、返回时置 false；`voice_utter` 在 `session_id` 分支里检查。

前端路由正确时走不到这个分支；它防的是前端出 bug 或有人直接打 API。

## 配置

`voice.answer_timeout_s: int = 8`（`gt=0`）—— 等待回答的静音超时。加在 `VoiceSection` 里，与既有 `wake_word` / `vad` 同级。

沿用 `VoiceCard.vue` 的设置项渲染（它与 `wake_word`/`vad` 同一张卡）。

## 测试策略

### 能自动验证（Vitest / pytest）

| 项 | 方式 |
|---|---|
| `matchOption` 精确匹配与不命中 | 纯函数单测，含「多空格/错字/否定短语 → 不命中」的对抗用例 |
| `handleTranscript` 的分流 | mock `api.transcribe` + `pendingQuestion`，断言走 `sendAnswer` 而非 `runTurn` |
| 状态机迁移表 | 迁移函数单测：合法/非法迁移 |
| `speaking` 代际计数防提前复位 | mock 两个 utterance，先触发旧的 `onend`，断言 `speaking` 仍为 true |
| 后端拒绝阻塞会话的新 utter | pytest：构造阻塞在 `ask()` 的会话，POST `/voice/utter` 带该 `session_id` → 400 |
| 播报→暂停/恢复的调用序列 | mock `WakeWordEngine`，断言 stop/start 的调用顺序与次数 |

### 不能自动验证（**必须人工**）

| 项 | 为什么 |
|---|---|
| 真实麦克风拾音与唤醒命中 | Vosk 是浏览器 WASM 引擎，Vitest（node/jsdom）无法驱动真实音频 |
| TTS 播报与监听的时序互斥 | 需真实扬声器；`echoCancellation` 的实际效果无法模拟 |
| VAD 静音超时 → 待机的真实体验 | 依赖真实环境噪声 |
| ASR 对中文选项的真实转写准确率 | 需真实 ASR 服务 |

**这些项在实施完成后由人工按脚本验证**，报告中会明确区分哪些结论来自自动化、哪些来自人工，不混为一谈。

### 人工验证脚本（实施后执行）

1. 发一条会触发提问的任务 → 播报结束后**直接开口**说答案 → 应被识别并作答
2. 重复 1，但在播报后**保持沉默 8s** → 应进入待机（界面显示待机文案）
3. 在待机态说「小逻小逻」→ 应回到**本题**继续作答，而不是开新一轮
4. 让助手播报一段**含「小逻小逻」**的文本 → 不应自触发唤醒
5. 用界面按钮回答（不经语音）→ 行为不变（回归）

## 风险

| 风险 | 处置 |
|---|---|
| `awaiting_answer` 自动开录可能把环境噪声当回答 | VAD 静音阈值已有配置；`answer_timeout_s` 可调；转写为空则不提交 |
| `stop()` 释放麦克风轨道会中断正在进行的录音 | 播报只发生在助手说话时（此时通常不在录音）；恢复逻辑按播报前状态回退 |
| 待机期间后端 `ask()` 一直阻塞 | **已定：不主动取消。**「待机」的语义就是「等用户回来」，主动取消提问等于放弃这次任务。用户想放弃可点停止或说取消（既有能力）。`answer_timeout_s` 只影响前端等待，不解除后端阻塞；`SESSION_TTL = 30min`（`api/state.py:17`）是最终兜底 |
| 新增状态值遗漏同步点 | 上表已列全部 6 处；实施时逐一核对，并以 `useAssistantVisuals` / `MiniHistory` 的人工验证兜底 |

## 不做（明确排除）

- 唤醒引擎的 `pause`/`mute`（引擎不提供，也不需要 —— `stop()`/`start()` 已够且不重载模型）
- 语音对 composite 类作答的选项部分（语音只填文本部分；选项仍点按钮）
- 模糊/容错的选项匹配（明确排除，见决策 3 的安全边界）
- 多语言唤醒词或更换 ASR 引擎
