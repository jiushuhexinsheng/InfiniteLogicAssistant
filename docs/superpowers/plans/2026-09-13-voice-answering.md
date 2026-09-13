# 语音作答 + 无应答待机 + 再唤醒续答 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让操作者能用语音回答提问（播报后自动开录、无应答待机、再唤醒续答本题），并修掉「一说话就把当前提问搞挂」的既有缺陷。

**Architecture:** 前端新增 `awaiting_answer` / `standby` 两个状态与显式迁移表，`handleTranscript` 按 `pendingQuestion` 分流到答案通道；`useTts` 暴露 `speaking` 信号驱动「播报期间暂停唤醒引擎」；后端给 `EventQueueChannel` 加 `awaiting_answer` 标志，`/voice/utter` 据此拒绝会覆盖阻塞会话的请求。

**Tech Stack:** Vue 3.4 + TypeScript + Vite 5 / vue-tsc / Vitest 4；Python 3.14 / FastAPI / pydantic v2 / pytest / mypy。

**Spec:** `docs/superpowers/specs/2026-09-13-voice-answering-design.md`

## Global Constraints

- 后端新增/修改的 docstring 必须**中英双语**；前端注释同样双语。
- **`matchOption` 只做 trim 后精确相等**，绝不做子串/模糊/大小写归一 —— 这是与确认层 `_resolve_confirm` 相同的安全边界，不要「顺手优化」成模糊匹配。
- **`AsstState` 新增两个值后，`useAssistantVisuals.STATE_VISUALS` 是 `Record<AsstState, StateVisual>`，会直接编译报错** —— 这是防遗漏机制，按报错补齐即可。但 **`MiniPlayer.ACTIVE_STATES`（数组）与 `MiniHistory`（模板 v-if 链）不会报错**，必须人工核对，别只依赖 `vue-tsc`。
- **Vosk 是浏览器 WASM 引擎，Vitest（node/jsdom）无法驱动真实音频** —— 唤醒引擎一律 mock（`globalThis.WakeWordEngine`），不要试图测真实拾音。
- 后端验证：`python -m pytest tests/ -q` + `python -m mypy core/ server.py`；前端：`cd web && npm test` + `npm run build`。
- TDD：先写失败测试 → 运行确认失败 → 最小实现 → 运行确认通过 → 提交。
- 每个 Task 结束跑**全量**回归，不只跑改动的那个文件（历史上循环导入只在全量下复现）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `web/src/composables/assistant/answerMatch.ts` | `matchOption`：转写文本 → 精确匹配选项 | Create |
| `web/src/composables/assistant/wakeFsm.ts` | 唤醒状态机迁移表（纯函数） | Create |
| `web/src/composables/assistant/useTts.ts` | 暴露 `speaking` 信号（含代际计数） | Modify |
| `web/src/composables/assistant/store.ts` | `AsstState` 增两值 | Modify |
| `web/src/composables/useAssistantVisuals.ts` | `STATE_VISUALS` 补两状态（编译强制） | Modify |
| `web/src/components/assistant/MiniPlayer.vue` | `ACTIVE_STATES` + 打断判定 | Modify |
| `web/src/components/assistant/MiniHistory.vue` | 状态文案 | Modify |
| `web/src/components/assistant/FloatBall.vue` | 录音视觉（`awaiting_answer` 同 `recording`） | Modify |
| `web/src/composables/assistant/useWakeWord.ts` | 迁移表 + `handleTranscript` 分流 + 播报门控 | Modify |
| `core/config/schema.py` | `VoiceSection.answer_timeout_s` | Modify |
| `config.yaml.example` | 补该项 | Modify |
| `web/src/components/console/settings/VoiceCard.vue` | 渲染该项 | Modify |
| `core/orchestrator/pipeline.py` | `EventQueueChannel.awaiting_answer` 标志 | Modify |
| `core/api/voice.py` | `/voice/utter` 拒绝阻塞会话 | Modify |

---

## Task 1: `matchOption` 精确匹配

**Files:**
- Create: `web/src/composables/assistant/answerMatch.ts`
- Test: `web/src/composables/assistant/__tests__/answerMatch.spec.ts`

**Interfaces:**
- Consumes: `QuestionOption`（`web/src/types.ts`，P4 已定义：`{ value: string; label: string }`）
- Produces: `matchOption(text: string, options: QuestionOption[]): QuestionOption | null`

- [ ] **Step 1: 写失败测试**

新建 `web/src/composables/assistant/__tests__/answerMatch.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { matchOption } from '../answerMatch'

const OPTS = [
  { value: 'yes', label: '允许本次' },
  { value: 'no', label: '拒绝' },
]

/** 转写文本 → 选项匹配：**只做 trim 后精确相等**。
 *  Transcript → option matching: trim-then-exact-equality only. */
describe('matchOption', () => {
  /** 精确命中返回对应选项。An exact hit returns the matching option. */
  it('精确命中返回选项', () => {
    expect(matchOption('允许本次', OPTS)?.value).toBe('yes')
    expect(matchOption('拒绝', OPTS)?.value).toBe('no')
  })

  /** 两侧空白被 trim 后仍命中。Surrounding whitespace is trimmed before comparing. */
  it('两侧空白 trim 后命中', () => {
    expect(matchOption('  允许本次  ', OPTS)?.value).toBe('yes')
  })

  /** 不命中返回 null。A miss returns null. */
  it('不命中返回 null', () => {
    expect(matchOption('好的', OPTS)).toBeNull()
    expect(matchOption('', OPTS)).toBeNull()
  })

  /** 子串不算命中 —— 这是安全边界，绝不能放宽为包含匹配。
   *  A substring is not a hit — this is the safety boundary and must never be relaxed
   *  to containment matching. */
  it('子串不命中（安全边界）', () => {
    expect(matchOption('我不允许本次', OPTS)).toBeNull()
    expect(matchOption('允许', OPTS)).toBeNull()
    expect(matchOption('拒绝吧', OPTS)).toBeNull()
  })

  /** 归一化一律不做：大小写/全角半角/标点差异都视为不命中。
   *  No normalisation at all: case, full/half-width and punctuation differences all miss. */
  it('不做任何归一化', () => {
    expect(matchOption('允许本次。', OPTS)).toBeNull()
    expect(matchOption('允许 本次', OPTS)).toBeNull()
  })

  /** 空选项列表返回 null。An empty option list returns null. */
  it('空选项列表返回 null', () => {
    expect(matchOption('允许本次', [])).toBeNull()
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/answerMatch.spec.ts`
Expected: FAIL — `Failed to resolve import "../answerMatch"`

- [ ] **Step 3: 实现**

新建 `web/src/composables/assistant/answerMatch.ts`：

```ts
import type { QuestionOption } from '../../types'

/**
 * 把语音转写文本匹配到某个选项。
 *
 * **只做 trim 后精确相等** —— 不做子串、模糊、大小写归一、全角半角转换或标点剥离。
 * 任何归一化都是模糊匹配的入口，而这条路径参与「是否批准执行」的判定，必须保守：
 * 不命中就返回 null，调用方按普通文本处理。
 *
 * Match a speech transcript against a question option.
 *
 * **Trim-then-exact-equality only** — no substring, fuzzy, case, width or punctuation
 * normalisation. Any normalisation is a gateway to fuzzy matching, and this path takes
 * part in deciding whether an action is approved, so it must stay conservative: a miss
 * returns null and the caller treats the text as plain input.
 *
 * @param text 转写文本。The transcript.
 * @param options 待匹配的选项列表。The options to match against.
 * @returns 命中的选项，未命中为 null。The matched option, or null.
 */
export function matchOption(text: string, options: QuestionOption[]): QuestionOption | null {
  const t = text.trim()
  if (!t) return null
  for (const opt of options) {
    if (t === opt.label.trim()) return opt
  }
  return null
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/answerMatch.spec.ts`
Expected: PASS（6 个用例）

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/answerMatch.ts web/src/composables/assistant/__tests__/answerMatch.spec.ts
git commit -m "feat(语音): 转写文本 → 选项精确匹配 matchOption

只做 trim 后精确相等，不做任何归一化 —— 子串/大小写/标点差异一律视为不命中。
这条路径参与「是否批准执行」的判定，与确认层 _resolve_confirm 同一安全边界。
测试含子串与归一化的对抗用例，防止日后被「顺手优化」成模糊匹配。"
```

---

## Task 2: `useTts` 暴露 `speaking` 信号

**Files:**
- Modify: `web/src/composables/assistant/useTts.ts`（`speakBrowser` 约 117 行、`speakApi` 约 137 行、`speakText` 约 161 行）
- Test: `web/src/composables/assistant/__tests__/useTts.spec.ts`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `speaking: Ref<boolean>`（从 `useTts()` 返回）；语义 = 「正在播报」

- [ ] **Step 1: 写失败测试**

新建 `web/src/composables/assistant/__tests__/useTts.spec.ts`：

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { speaking, speakText } from '../useTts'

/**
 * 播报完成信号：门控必须覆盖整个播报时长，不是调用那一刻。
 * Speech completion signal: gating must span the whole utterance, not the call instant.
 */
describe('useTts speaking 信号', () => {
  let utterances: any[]

  beforeEach(() => {
    utterances = []
    speaking.value = false
    ;(globalThis as any).window = globalThis
    // SpeechSynthesisUtterance 桩：记录实例供测试手动触发 onend。
    // Stub that records instances so the test can fire onend manually.
    ;(globalThis as any).SpeechSynthesisUtterance = class {
      text: string
      onend: (() => void) | null = null
      onerror: (() => void) | null = null
      constructor(text: string) { this.text = text; utterances.push(this) }
    }
    ;(globalThis as any).speechSynthesis = { cancel: vi.fn(), speak: vi.fn() }
    ;(globalThis as any).requestAnimationFrame = (fn: () => void) => { fn(); return 0 }
  })

  /** 播报开始即置 true。speaking turns true as soon as playback starts. */
  it('播报开始置 true，onend 置 false', () => {
    speakText('你好')
    expect(speaking.value).toBe(true)
    utterances[0].onend?.()
    expect(speaking.value).toBe(false)
  })

  /** onerror 也要复位，否则一次失败会让门控永久关闭。 */
  it('onerror 同样复位', () => {
    speakText('你好')
    utterances[0].onerror?.()
    expect(speaking.value).toBe(false)
  })

  /** 代际计数：连续两次播报时，第一次迟到的 onend 不得把第二次的 speaking 提前置 false。
   *  Generation counter: with back-to-back utterances, a late onend from the first must
   *  not clear the second's speaking flag early. */
  it('旧播报迟到的 onend 不提前复位', () => {
    speakText('第一句')
    speakText('第二句')
    expect(speaking.value).toBe(true)
    utterances[0].onend?.()          // 第一句的 onend 迟到
    expect(speaking.value).toBe(true) // 第二句仍在播
    utterances[1].onend?.()
    expect(speaking.value).toBe(false)
  })

  /** 未启用播报（总开关关闭）时不置 speaking。When auto-broadcast is off, speaking stays false. */
  it('未启用时不置 speaking', () => {
    speakText('')                    // 空文本直接返回
    expect(speaking.value).toBe(false)
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/useTts.spec.ts`
Expected: FAIL — 未导出 `speaking`

- [ ] **Step 3: 实现**

`web/src/composables/assistant/useTts.ts` —— 顶部（`ttsSettings` 附近）加：

```ts
/** 是否正在播报。门控唤醒引擎用：播报期间暂停监听，避免助手自己的声音自触发唤醒。
 *  Whether speech is currently playing. Used to gate the wake engine: listening is paused
 *  during playback so the assistant's own voice cannot self-trigger the wake word. */
export const speaking = ref(false)

/** 播报代际：连续播报时，旧播报迟到的 onend 不得复位新一轮的 speaking。
 *  Playback generation: with back-to-back utterances, a late onend from an older
 *  utterance must not clear the newer one's speaking flag. */
let speakGen = 0
```

`speakBrowser` 改为：

```ts
function speakBrowser(text: string) {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  try {
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text.replace(/\n/g, '，'))
    const s = ttsSettings.value
    u.volume = s.volume
    u.rate = s.rate
    u.pitch = s.pitch
    const v = resolveVoice()
    if (v) { u.voice = v; u.lang = v.lang } else { u.lang = 'zh-CN' }
    // 代际计数：只有本轮播报的结束回调才允许复位 speaking
    // Generation counter: only this round's completion callback may clear speaking.
    const gen = ++speakGen
    speaking.value = true
    const done = () => { if (gen === speakGen) speaking.value = false }
    u.onend = done
    u.onerror = done
    requestAnimationFrame(() => {
      try { window.speechSynthesis.speak(u) } catch { /* ignore */ }
    })
  } catch { /* ignore */ }
}
```

`speakApi` 的音频回调改为：

```ts
    const gen = ++speakGen
    speaking.value = true
    const done = () => {
      if (gen === speakGen) speaking.value = false
      URL.revokeObjectURL(url)
    }
    audio.onended = done
    audio.onerror = () => { done(); speakBrowser(text) }
    await audio.play().catch(() => { done(); speakBrowser(text) })
```

（注意：回退到 `speakBrowser` 时它会自己再 `++speakGen` 并置 `speaking = true`，故先 `done()` 再回退不会闪断。）

`useTts()` 的返回对象加 `speaking`。

- [ ] **Step 4: 运行确认通过**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/useTts.spec.ts && npx vue-tsc --noEmit`
Expected: PASS，类型无错

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/useTts.ts web/src/composables/assistant/__tests__/useTts.spec.ts
git commit -m "feat(语音): useTts 暴露 speaking 信号（含代际计数）

speakText 原是同步 void、无完成信号，而唤醒门控必须覆盖整个播报时长。
两条播报路径的 onend/onerror 钩子本就存在但未被使用，现接上。

代际计数解决一个并发陷阱：speakBrowser 会先 speechSynthesis.cancel()，
上一个 utterance 的 onend 可能迟到并把新一轮的 speaking 提前置 false。
测试用两个连续播报验证了该场景。"
```

---

## Task 3: `AsstState` 新增两值 + 同步点

**Files:**
- Modify: `web/src/composables/assistant/store.ts:6-15`
- Modify: `web/src/composables/useAssistantVisuals.ts:20-31`（`STATE_VISUALS`）
- Modify: `web/src/components/assistant/MiniPlayer.vue:65,82`
- Modify: `web/src/components/assistant/MiniHistory.vue:6-12`
- Modify: `web/src/components/assistant/FloatBall.vue:203,211`
- Test: `web/src/components/assistant/__tests__/MiniHistory.spec.ts`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `AsstState` 新增 `'awaiting_answer' | 'standby'`

- [ ] **Step 1: 写失败测试**

新建 `web/src/components/assistant/__tests__/MiniHistory.spec.ts`：

```ts
// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MiniHistory from '../MiniHistory.vue'

/** 新状态在迷你历史里要有明确文案（否则用户不知道系统在等什么）。
 *  The new states need explicit copy in the mini history, or the user cannot tell what
 *  the system is waiting for. */
describe('MiniHistory 新状态文案', () => {
  const base = { turns: [], wakeKeyword: '小逻小逻', partialText: '' }

  it('awaiting_answer 提示可直接开口作答', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'awaiting_answer' as any } })
    expect(w.text()).toContain('回答')
  })

  it('standby 提示先说唤醒词再继续作答', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'standby' as any } })
    expect(w.text()).toContain('小逻小逻')
  })

  it('原有 listening 文案不变（回归）', () => {
    const w = mount(MiniHistory, { props: { ...base, state: 'listening' as any } })
    expect(w.text()).toContain('聆听中')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/components/assistant/__tests__/MiniHistory.spec.ts`
Expected: FAIL — 新状态落到 `v-else` 的默认文案，不含「回答」

- [ ] **Step 3: 实现**

`store.ts` 的 `AsstState` 加两值：

```ts
export type AsstState =
  | 'idle'
  | 'listening'
  /** 等待操作者回答某个提问（转写将走答案通道，而非开新一轮）。 */
  /** Waiting for the operator to answer a question (the transcript goes to the answer channel, not a new turn). */
  | 'awaiting_answer'
  /** 等待回答超时后的待机：引擎仍在听唤醒词，唤醒后回到**本题**续答。 */
  /** Standby after the answer timeout: the engine still listens for the wake word, and waking resumes *this* question. */
  | 'standby'
  | 'recording'
  | 'transcribing'
  | 'thinking'
  | 'tool_calling'
  | 'responding'
  | 'done'
  | 'error'
```

`useAssistantVisuals.ts` 的 `STATE_VISUALS` 补两项（`Record<AsstState, ...>` 会强制你补，否则 vue-tsc 报错）：

```ts
  awaiting_answer: { icon: 'mic',      label: '请回答…',                  color: '#f59e0b', fx: 'fx-recording',     grad: 'rainbow' },
  standby:         { icon: 'ear',      label: kw => `待机中…说"${kw}"继续`, color: '#94a3b8', fx: 'fx-idle',          grad: 'brand' },
```

`MiniPlayer.vue`：

```ts
const ACTIVE_STATES: AsstState[] = ['listening', 'recording', 'awaiting_answer', 'transcribing', 'thinking', 'tool_calling', 'responding']
```
```ts
  if (p && ['recording', 'listening', 'awaiting_answer'].includes(props.state)) return p
```

`MiniHistory.vue` 的 `v-if` 链在 `listening` 分支之后插入：

```vue
      <template v-else-if="state === 'awaiting_answer'">🎤 请直接说出你的回答…</template>
      <template v-else-if="state === 'standby'">💤 待机中，说"{{ wakeKeyword }}"继续回答</template>
```

`FloatBall.vue` 的两处 `recording` 判定改为同时认 `awaiting_answer`：

```ts
watch(() => props.state, (s) => {
  if (s === 'recording' || s === 'awaiting_answer') startProgress()
  else stopProgress()
})
```
```ts
  if (props.state !== 'recording' && props.state !== 'awaiting_answer') return {}
```

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: 全部通过。

> **注意**：`STATE_VISUALS` 会因缺项而编译报错，那是**防遗漏机制**，按报错补齐即可。但 **`ACTIVE_STATES`（数组）与 `MiniHistory`（模板）不会报错** —— 它们是否有遗漏只能靠人工核对（本 Task 的 6 处同步点已逐一列出）。

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/store.ts web/src/composables/useAssistantVisuals.ts web/src/components/assistant/
git commit -m "feat(语音): AsstState 新增 awaiting_answer / standby 两状态

把「等待回答」与「待机」从既有 recording/listening 中区分出来：
- recording 是说完唤醒词后录音；awaiting_answer 是系统在等某个提问的答案，两者转写去向不同
- listening 唤醒后开新一轮；standby 唤醒后续答本题

同步了 6 处：store 类型 / STATE_VISUALS（Record<AsstState> 编译强制）/
MiniPlayer 的 ACTIVE_STATES 与打断判定 / MiniHistory 文案 / FloatBall 录音视觉。
后四处不报编译错，靠人工核对。"
```

---

## Task 4: `handleTranscript` 分流（核心修复）

**Files:**
- Modify: `web/src/composables/assistant/useWakeWord.ts`（`handleTranscript` 约 240-258 行）
- Test: `web/src/composables/assistant/__tests__/useWakeWord.spec.ts`（追加）

**Interfaces:**
- Consumes: Task 1 的 `matchOption`；`pendingQuestion`（P4 的 `{ text, kind, options }`）；`sendAnswer(text, choice?)`
- Produces: `handleTranscript(blob: Blob): Promise<void>` **导出**（供测试驱动）

- [ ] **Step 1: 写失败测试**

在 `tests`/`src/composables/assistant/__tests__/useWakeWord.spec.ts` 追加（沿用该文件已有的 `vi.resetModules()` + 动态 import 风格）：

```ts
/** 提问待答时的转写必须走答案通道，而不是开新一轮 —— 这是「一说话就把当前提问搞挂」的根因修复。
 *  A transcript while a question is pending must go to the answer channel, not start a new
 *  turn — this is the fix for "speaking hangs the pending question". */
describe('useWakeWord handleTranscript 分流', () => {
  beforeEach(() => {
    vi.resetModules()
    ;(globalThis as any).WakeWordEngine = { init: vi.fn(async () => true) }
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network')))
  })

  /** 有待答提问 → 走 sendAnswer，不开新一轮。 */
  it('有待答提问时走答案通道', async () => {
    const apiMod = await import('../../../api')
    const store = await import('../store')
    const chat = await import('../useChat')
    vi.spyOn(apiMod.api, 'transcribe').mockResolvedValue({ ok: true, text: '允许本次' } as any)
    const sendSpy = vi.spyOn(chat, 'sendAnswer').mockResolvedValue(undefined as any)
    const turnSpy = vi.spyOn(chat, 'runTurn').mockResolvedValue(undefined as any)
    store.currentSessionId.value = 's1'
    store.pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '允许本次' }, { value: 'no', label: '拒绝' }],
    }
    store.messages.value = []

    const { handleTranscript } = await import('../useWakeWord')
    await handleTranscript(new Blob(['x']))

    expect(sendSpy).toHaveBeenCalledWith('', 'yes')   // 命中 label → 回传对应 value
    expect(turnSpy).not.toHaveBeenCalled()
    expect(store.messages.value).toHaveLength(0)       // 不再写入 user 消息
  })

  /** 有待答提问但文本不命中任何选项 → 作为普通文本作答。 */
  it('未命中选项时作为文本作答', async () => {
    const apiMod = await import('../../../api')
    const store = await import('../store')
    const chat = await import('../useChat')
    vi.spyOn(apiMod.api, 'transcribe').mockResolvedValue({ ok: true, text: '随便吧' } as any)
    const sendSpy = vi.spyOn(chat, 'sendAnswer').mockResolvedValue(undefined as any)
    const turnSpy = vi.spyOn(chat, 'runTurn').mockResolvedValue(undefined as any)
    store.currentSessionId.value = 's1'
    store.pendingQuestion.value = {
      text: '确认执行吗？', kind: 'choice',
      options: [{ value: 'yes', label: '允许本次' }],
    }

    const { handleTranscript } = await import('../useWakeWord')
    await handleTranscript(new Blob(['x']))

    expect(sendSpy).toHaveBeenCalledWith('随便吧', undefined)
    expect(turnSpy).not.toHaveBeenCalled()
  })

  /** 无待答提问 → 维持原行为（写入 user 消息 + 开新一轮）。回归。 */
  it('无待答提问时维持原行为', async () => {
    const apiMod = await import('../../../api')
    const store = await import('../store')
    const chat = await import('../useChat')
    vi.spyOn(apiMod.api, 'transcribe').mockResolvedValue({ ok: true, text: '你好' } as any)
    const sendSpy = vi.spyOn(chat, 'sendAnswer').mockResolvedValue(undefined as any)
    const turnSpy = vi.spyOn(chat, 'runTurn').mockResolvedValue(undefined as any)
    store.pendingQuestion.value = null
    store.messages.value = []

    const { handleTranscript } = await import('../useWakeWord')
    await handleTranscript(new Blob(['x']))

    expect(turnSpy).toHaveBeenCalled()
    expect(sendSpy).not.toHaveBeenCalled()
    expect(store.messages.value.some((m) => m.text === '你好')).toBe(true)
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/useWakeWord.spec.ts`
Expected: FAIL — `handleTranscript` 未导出（`is not a function`）

- [ ] **Step 3: 实现**

`useWakeWord.ts` —— import 段加：

```ts
import { matchOption } from './answerMatch'
import { pendingQuestion } from './store'
import { sendAnswer } from './useChat'
```

（若这些符号已在既有的 `from './store'` / `from './useChat'` 多符号导入里，则并入既有行，不要重复 import。）

`handleTranscript` 改为**导出**并加分流：

```ts
/** ASR 转写处理：提问待答时走答案通道，否则开新一轮。
 *
 * 提问待答时**绝不能**走 runTurn —— 那会开一条新的 /voice/utter 并 abort 掉当前流，
 * 使后端阻塞中的 ask() 永久挂死（这正是本设计要修的既有缺陷）。
 *
 * ASR transcription handling: a pending question routes to the answer channel, otherwise
 * a new turn starts. While a question is pending it must NEVER call runTurn — that opens a
 * new /voice/utter and aborts the current stream, leaving the backend's blocked ask()
 * hanging forever (the existing defect this design fixes).
 *
 * @param blob 录音音频。The recorded audio.
 */
export async function handleTranscript(blob: Blob) {
  try {
    const r = await api.transcribe(blob)
    if (r.ok && r.text) {
      const text = r.text.trim()
      if (!text) { state.value = 'listening'; return }
      partialText.value = text
      const pq = pendingQuestion.value
      if (pq) {
        // 精确匹配到选项则回传该选项的 value；否则整段作为文本作答。
        // An exact option match returns that option's value; otherwise the whole text is
        // submitted as free text.
        const matched = matchOption(text, pq.options)
        await sendAnswer(matched ? '' : text, matched?.value)
        return
      }
      addMessage('user', text)
      await runTurn()
    } else {
      addMessage('system', '转写失败：' + (r.error || '无结果'))
      state.value = 'listening'
    }
  } catch (e) {
    console.error('[Asst] transcribe error:', e)
    addMessage('system', '转写异常：' + formatError(e))
    state.value = 'error'
  }
}
```

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/useWakeWord.ts web/src/composables/assistant/__tests__/useWakeWord.spec.ts
git commit -m "fix(语音): 提问待答时转写走答案通道，不再开新一轮

原 handleTranscript 无 pendingQuestion 分支，转写一律 addMessage + runTurn，
而 runTurn 会 abort 当前流 → 后端阻塞中的 ask() 永久挂死。这是本设计的核心修复。

选项命中（trim 精确相等）则回传该选项 value，否则整段作为文本作答。
handleTranscript 改为导出以便测试驱动；三个用例覆盖命中/未命中/无待答提问。"
```

---

## Task 5: 状态机迁移表（进入待答 / 超时待机 / 再唤醒续答）

> **本任务是功能主干**：Task 3 只加了状态值、Task 4 只做了转写分流，而「播报后自动开录」
> 「无应答进待机」「再唤醒续答本题」这三个动作尚无实现。缺了它，新状态永远不会被进入。

**Files:**
- Create: `web/src/composables/assistant/wakeFsm.ts`
- Modify: `web/src/composables/assistant/useWakeWord.ts`（`startVAD` 约 130-173 行、`startMaxTimer` 约 176-182 行、`onWakeDetected` 约 185 行、`toggleWake` 约 262 行）
- Test: `web/src/composables/assistant/__tests__/wakeFsm.spec.ts`（新建）

**Interfaces:**
- Consumes: Task 3 的 `AsstState`
- Produces: `WakeEvent`（`'question_ready' | 'speech_started' | 'speech_done' | 'answer_timeout' | 'wake_detected' | 'wake_toggled_off'`）；`nextState(current: AsstState, event: WakeEvent): AsstState`

- [ ] **Step 1: 写失败测试**

新建 `web/src/composables/assistant/__tests__/wakeFsm.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { nextState } from '../wakeFsm'

/**
 * 唤醒状态机迁移表（纯函数）。抽出来是因为真实录音路径依赖 MediaRecorder/AudioContext，
 * jsdom 里跑不了；迁移决策与副作用分开后，决策可以穷尽测试。
 *
 * The wake state machine transition table (a pure function). It is extracted because the
 * real recording path needs MediaRecorder/AudioContext, unavailable under jsdom; splitting
 * the decision from the effects makes the decision exhaustively testable.
 */
describe('wakeFsm 迁移表', () => {
  /** 提问就绪 → 进入待答（自动开录）。 */
  it('question_ready → awaiting_answer', () => {
    expect(nextState('responding', 'question_ready')).toBe('awaiting_answer')
    expect(nextState('thinking', 'question_ready')).toBe('awaiting_answer')
  })

  /** 待答超时（用户全程未说话）→ 待机。 */
  it('answer_timeout 在待答态 → standby', () => {
    expect(nextState('awaiting_answer', 'answer_timeout')).toBe('standby')
  })

  /** 待机时再唤醒 → 回到待答（续答本题），而不是开新一轮。 */
  it('待机态 wake_detected → awaiting_answer（续答本题）', () => {
    expect(nextState('standby', 'wake_detected')).toBe('awaiting_answer')
  })

  /** 普通 listening 态唤醒 → recording（开新一轮），行为不变。 */
  it('listening 态 wake_detected → recording（回归）', () => {
    expect(nextState('listening', 'wake_detected')).toBe('recording')
  })

  /** 待答态检测到语音 → 保持待答（交回既有 VAD 静音逻辑收尾）。 */
  it('待答态 speech_started 保持 awaiting_answer', () => {
    expect(nextState('awaiting_answer', 'speech_started')).toBe('awaiting_answer')
  })

  /** 关了唤醒开关 → idle。 */
  it('wake_toggled_off → idle', () => {
    expect(nextState('standby', 'wake_toggled_off')).toBe('idle')
    expect(nextState('awaiting_answer', 'wake_toggled_off')).toBe('idle')
  })

  /** 无关组合保持不变，不抛错。 */
  it('无关事件不改变状态', () => {
    expect(nextState('idle', 'speech_started')).toBe('idle')
    expect(nextState('thinking', 'answer_timeout')).toBe('thinking')
    expect(nextState('recording', 'question_ready')).toBe('recording')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/wakeFsm.spec.ts`
Expected: FAIL — `Failed to resolve import "../wakeFsm"`

- [ ] **Step 3: 实现（纯函数 + 接线）**

新建 `web/src/composables/assistant/wakeFsm.ts`：

```ts
import type { AsstState } from './store'

/** 唤醒状态机的事件。Events of the wake state machine. */
export type WakeEvent =
  /** 提问就绪（已被播报）→ 应自动开录等待作答。 */
  | 'question_ready'
  /** 本次录音里首次检测到语音。 */
  | 'speech_started'
  /** 本次录音正常结束（有待转写内容）。 */
  | 'speech_done'
  /** 等待作答超时（全程未说话）。 */
  | 'answer_timeout'
  /** 唤醒词命中。 */
  | 'wake_detected'
  /** 唤醒功能被关闭。 */
  | 'wake_toggled_off'

/**
 * 唤醒状态机迁移表。
 *
 * 只处理与「等待作答」相关的迁移，其余组合原样返回当前状态 —— 这样它不会与既有的
 * 散落赋值冲突，接入时可以逐处替换而非一次性重写。
 *
 * Wake state-machine transition table. It only covers transitions related to awaiting an
 * answer; every other combination returns the current state unchanged, so it can be wired
 * in incrementally instead of forcing a rewrite of the existing scattered assignments.
 *
 * @param current 当前状态。The current state.
 * @param event 触发事件。The triggering event.
 * @returns 迁移后的状态。The resulting state.
 */
export function nextState(current: AsstState, event: WakeEvent): AsstState {
  if (event === 'wake_toggled_off') return 'idle'

  switch (event) {
    case 'question_ready':
      // 提问已播报完 → 自动进入待答（§决策 1：不必再说唤醒词）
      // The question has been spoken → start awaiting the answer automatically.
      return current === 'responding' || current === 'thinking' || current === 'done'
        ? 'awaiting_answer'
        : current

    case 'answer_timeout':
      // 只有待答态的超时才进待机；其它状态的超时与本题无关
      // Only the answer-wait timeout enters standby; other timeouts are unrelated.
      return current === 'awaiting_answer' ? 'standby' : current

    case 'wake_detected':
      // 待机态唤醒 → 续答本题；其余态维持既有行为（由调用方置 recording）
      // Waking from standby resumes this question; other states keep existing behaviour.
      return current === 'standby' ? 'awaiting_answer' : current

    case 'speech_started':
      // 待答态检测到语音后交回既有 VAD 静音逻辑收尾，状态不变
      // Once speech starts, the existing VAD silence logic finishes the recording.
      return current

    case 'speech_done':
      return current
  }
}
```

**接线到 `useWakeWord.ts`**（各处按下列改，不要重写整个文件）：

1. import 段加：
```ts
import { nextState } from './wakeFsm'
import { speaking } from './useTts'
```

2. `startVAD` 里，`minSpeakTime` 之后加一个「是否已开始说话」标志，供待答态使用：
```ts
  const minSpeakTime = 2000
  let speechStarted = false
```
在 `if (rms < threshold) { ... }` 的 `else` 分支里置位并上报：
```ts
    } else {
      silenceCount = 0
      if (!speechStarted) {
        speechStarted = true
        const ns = nextState(state.value, 'speech_started')
        if (ns !== state.value) state.value = ns
      }
    }
```

3. `startMaxTimer` 参数化（待答态用 `answer_timeout_s`，其余沿用 `vad.max_duration_ms`）：
```ts
/** 启动最大录音时长定时器。`ms` 缺省用 VAD 的 max_duration_ms。
 *  Start the max recording timer; `ms` defaults to the VAD's max_duration_ms. */
function startMaxTimer(ms?: number) {
  maxTimer = setTimeout(() => {
    console.log('[Asst] max duration reached')
    // 待答态超时 = 全程未说话 → 进待机；其余态维持既有行为
    // An answer-wait timeout means the user never spoke → standby.
    const ns = nextState(state.value, 'answer_timeout')
    if (ns !== state.value) { state.value = ns; stopRecording({ silent: true }); return }
    stopRecording()
  }, ms ?? (vadConfig.max_duration_ms || 10000))
}
```

4. `stopRecording` 增加可选参数（待答超时时不转写、直接回待机）：
```ts
function stopRecording(opts?: { silent?: boolean }) {
  // …既有清理逻辑不变；在 onstop 里按 silent 决定是否走 handleTranscript
```
在 `wakeRecorder.onstop` 回调里：
```ts
    if (opts?.silent) {
      // 待答超时：无音频可转写，已置 standby，直接返回
      // Answer wait timed out: nothing to transcribe; standby was already set.
      return
    }
```

5. `onWakeDetected` 开头按状态分流：
```ts
function onWakeDetected() {
  console.log('[Asst] WAKE!')
  // 待机态唤醒 → 续答本题（不重新计一轮）；其余态维持既有行为
  // Waking from standby resumes this question rather than starting a new round.
  const ns = nextState(state.value, 'wake_detected')
  state.value = ns === 'awaiting_answer' ? 'awaiting_answer' : 'recording'
  if (ns !== 'awaiting_answer') playBeep()
  if (ns === 'awaiting_answer') startMaxTimer(answerTimeoutMs())
  else startMaxTimer()
  // …其余逻辑（取 stream、建 MediaRecorder）不变
```

6. 新增一个取超时值的小助手：
```ts
/** 待答时长（毫秒）。Answer-wait duration in milliseconds. */
function answerTimeoutMs(): number {
  const s = (wakeConfig as { answer_timeout_s?: number }).answer_timeout_s
  return (s && s > 0 ? s : 8) * 1000
}
```

7. 播报结束后进入待答：在 Task 6 的门控 watch 里，`speaking` 变 false 时若 `pendingQuestion` 非空则 `state.value = nextState(state.value, 'question_ready')` 并启动一次录音（复用 `onWakeDetected` 的录音建立逻辑，抽出为 `startRecording()`）。

> **实施提示**：第 7 步需要把 `onWakeDetected` 里「取 stream + 建 MediaRecorder + startVAD + startMaxTimer」那段抽成 `startRecording()`，供唤醒与「播报后自动开录」共用。这是本 Task 唯一的结构性改动，不要复制粘贴两份录音逻辑。

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/wakeFsm.spec.ts && npm test && npm run build`
Expected: 全部通过

> **注意**：录音与 VAD 的真实行为**无法在 jsdom 中验证**（需 MediaRecorder/AudioContext），
> 故本 Task 的自动化只覆盖**迁移决策**；「是否真的自动开录」「超时是否真的 8s」属 Task 9 的人工验证。

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/wakeFsm.ts web/src/composables/assistant/useWakeWord.ts web/src/composables/assistant/__tests__/wakeFsm.spec.ts
git commit -m "feat(语音): 唤醒状态机迁移表 + 待答/待机/续答接线

Task 3 只加了状态值、Task 4 只做了转写分流，本 Task 补上产生这些状态的迁移：
- question_ready（播报完）→ awaiting_answer，自动开录
- answer_timeout（待答态全程未说话）→ standby
- wake_detected（待机态）→ awaiting_answer，续答本题

迁移抽成纯函数 wakeFsm.nextState：真实录音路径依赖 MediaRecorder/AudioContext，
jsdom 跑不了，故决策与副作用分离后决策可穷尽测试。

配套改动：startMaxTimer 参数化（待答用 answer_timeout_s）、VAD 加 speechStarted
标志（待答态检测到语音后交回既有静音逻辑）、录音建立逻辑抽成 startRecording()
供唤醒与「播报后自动开录」共用（避免两份录音逻辑）。"
```

---

## Task 6: 播报期间暂停监听

**Files:**
- Modify: `web/src/composables/assistant/useWakeWord.ts`（顶部 import + 新增 watch）
- Test: `web/src/composables/assistant/__tests__/useWakeWord.spec.ts`（追加）

**Interfaces:**
- Consumes: Task 2 的 `speaking`（`useTts`）
- Produces: 无新接口

- [ ] **Step 1: 写失败测试**

追加：

```ts
/** 播报期间暂停监听，播完恢复 —— 消除助手自己的声音自触发唤醒。
 *  Listening is paused during playback and resumed after, so the assistant's own voice
 *  cannot self-trigger the wake word. */
describe('useWakeWord 播报门控', () => {
  beforeEach(() => {
    vi.resetModules()
    // 桩必须【有状态】：isRunning 要反映 stop/start 的调用，否则 start() 的
    // 「!isRunning() 才重启」判定永远为假，测试会假失败。
    // The stub must be STATEFUL: isRunning has to reflect stop/start calls, otherwise the
    // "restart only when !isRunning()" check is always false and the test fails spuriously.
    let running = true
    ;(globalThis as any).WakeWordEngine = {
      init: vi.fn(async () => true),
      start: vi.fn(async () => { running = true; return true }),
      stop: vi.fn(() => { running = false }),
      isRunning: vi.fn(() => running),
      isModelLoaded: vi.fn(() => true),
    }
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no network')))
  })

  it('speaking 变 true 时停止引擎，变 false 时重启', async () => {
    const store = await import('../store')
    store.wakeEnabled.value = true          // 唤醒开关打开，才应恢复监听
    const tts = await import('../useTts')
    await import('../useWakeWord')          // 触发 watch 注册
    await nextTick()
    const eng = (globalThis as any).WakeWordEngine
    eng.stop.mockClear(); eng.start.mockClear()

    tts.speaking.value = true
    await nextTick()
    expect(eng.stop).toHaveBeenCalledTimes(1)
    expect(eng.isRunning()).toBe(false)     // 桩确实变成了未运行

    tts.speaking.value = false
    await nextTick()
    expect(eng.start).toHaveBeenCalledTimes(1)
  })

  /** 唤醒开关关闭时不恢复监听（避免「关了唤醒却被动开麦」）。 */
  it('唤醒开关关闭时播完不重启', async () => {
    const store = await import('../store')
    store.wakeEnabled.value = false
    const tts = await import('../useTts')
    await import('../useWakeWord')
    await nextTick()
    const eng = (globalThis as any).WakeWordEngine
    eng.stop.mockClear(); eng.start.mockClear()

    tts.speaking.value = true
    await nextTick()
    tts.speaking.value = false
    await nextTick()
    expect(eng.start).not.toHaveBeenCalled()
  })
})
```

（该文件顶部需 `import { nextTick } from 'vue'`。）

- [ ] **Step 2: 运行确认失败**

Run: `cd web && npx vitest run src/composables/assistant/__tests__/useWakeWord.spec.ts`
Expected: FAIL — `eng.stop` 未被调用（无门控）

- [ ] **Step 3: 实现**

`useWakeWord.ts` —— import 段加 `import { speaking } from './useTts'` 与 `import { watch } from 'vue'`（若未导入），并加一个模块级 watch：

```ts
/**
 * 播报期间暂停唤醒引擎，播完恢复。
 *
 * 引擎只有 stop/start、没有 pause；stop() 会释放麦克风轨道，start() 只重建流与
 * recognizer（**不重载模型**），故成本可接受。这样助手播报里即便含唤醒词也不会
 * 自触发 —— echoCancellation 只能缓解，不能消除。
 *
 * Pause the wake engine during playback and resume after. The engine offers stop/start
 * but no pause; stop() releases the mic track and start() only rebuilds the stream and
 * recognizer (**no model reload**), so the cost is acceptable. This stops the
 * assistant's own speech from self-triggering the wake word — echoCancellation only
 * mitigates that, it does not eliminate it.
 */
watch(speaking, (isSpeaking) => {
  const eng = (globalThis as { WakeWordEngine?: any }).WakeWordEngine
  if (!eng) return
  if (isSpeaking) {
    if (eng.isRunning?.()) eng.stop()
  } else if (wakeEnabled.value) {
    // 播报前若在监听/待机/等待回答，播完恢复监听；否则保持停止。
    // Resume listening only if we were listening before playback started.
    if (eng.isModelLoaded?.() && !eng.isRunning?.()) void eng.start()
  }
})
```

- [ ] **Step 4: 运行确认通过 + 全量前端回归**

Run: `cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add web/src/composables/assistant/useWakeWord.ts web/src/composables/assistant/__tests__/useWakeWord.spec.ts
git commit -m "feat(语音): 播报期间暂停唤醒引擎，消除自触发

引擎无 pause，只有 stop/start；已确认 start() 不重载模型（只重建麦克风流与
recognizer），成本可接受。echoCancellation 只能缓解自触发、无法消除 ——
助手播报里含唤醒词时仍会被识别。"
```

---

## Task 7: 后端 `answer_timeout_s` 配置

**Files:**
- Modify: `core/config/schema.py`（`VoiceSection` 约 173-184 行）
- Modify: `core/config/runtime.py`（`editable_snapshot()` 的 `voice` 相关键）
- Modify: `config.yaml.example`
- Modify: `web/src/components/console/settings/VoiceCard.vue`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `settings.voice.answer_timeout_s: int`（默认 8，`gt=0`）

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 追加：

```python
def test_voice_answer_timeout_default_and_bounds():
    """等待回答的静音超时：默认 8s，必须为正数（0 或负数会让等待立即超时）。
    The answer-wait silence timeout defaults to 8s and must be positive (0 or negative
    would time out immediately)."""
    assert c.Settings().voice.answer_timeout_s == 8
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.Settings(voice={"answer_timeout_s": 0})
    with pytest.raises(ValidationError):
        c.Settings(voice={"answer_timeout_s": -1})


def test_voice_answer_timeout_in_snapshot(monkeypatch):
    """可编辑快照必须暴露该项，否则设置页拿不到。
    The editable snapshot must expose it, or the settings page cannot read it."""
    monkeypatch.setattr(c, "get_settings", lambda: c.Settings(voice={"answer_timeout_s": 12}))
    snap = c.editable_snapshot()
    assert snap["voice_timeout"]["answer_timeout_s"] == 12
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_config.py -q -k answer_timeout`
Expected: FAIL — `AttributeError: 'VoiceSection' object has no attribute 'answer_timeout_s'`

- [ ] **Step 3: 实现**

`core/config/schema.py` 的 `VoiceSection` 加字段：

```python
    # 等待操作者语音回答的静音超时（秒）：超时无语音则进入待机。
    # Silence timeout (seconds) while waiting for a spoken answer; on timeout the
    # assistant enters standby.
    answer_timeout_s: int = Field(8, gt=0)
```

`core/config/runtime.py` 的 `editable_snapshot()` 返回字典里，与 `"wake_word"`/`"vad"` 同级加：

```python
        "voice_timeout": {"answer_timeout_s": s.voice.answer_timeout_s},
```

`config.yaml.example` 的 `voice:` 段内加：

```yaml
  # 等待操作者语音回答的静音超时（秒）：超时无语音则进入待机（引擎仍听唤醒词）。
  # Silence timeout (seconds) while waiting for a spoken answer; on timeout the
  # assistant enters standby (the engine still listens for the wake word).
  answer_timeout_s: 8
```

`web/src/components/console/settings/VoiceCard.vue` —— 在 VAD 字段之后加一个 `SettingsField`：

```vue
    <SettingsField v-if="s.editable.value" label="等待回答超时（秒）">
      <UiInput type="number" min="1" :model-value="s.editable.value.voice_timeout.answer_timeout_s"
               @update:model-value="v => { const e = s.editable.value as any; if (e) e.voice_timeout.answer_timeout_s = toNum(v) }" />
    </SettingsField>
```

并在 `state.ts` 的 `moduleBody('voice')` 里把它带上：

```ts
  if (id === 'voice') return {
    wake_word: e.wake_word, vad: e.vad,
    answer_timeout_s: e.voice_timeout.answer_timeout_s,
  }
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_config.py -q && python -m mypy core/ server.py && cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/config/schema.py core/config/runtime.py config.yaml.example web/src/components/console/settings tests/test_config.py
git commit -m "feat(配置): 新增 voice.answer_timeout_s（等待语音回答的静音超时）

默认 8s，必须为正数。快照里以 voice_timeout 暴露（与 wake_word/vad 同级），
moduleBody('voice') 同步带上，否则保存时会被丢掉。"
```

---

## Task 8: `/voice/utter` 拒绝阻塞中的会话

**Files:**
- Modify: `core/orchestrator/pipeline.py`（`EventQueueChannel`）
- Modify: `core/api/voice.py`（`voice_utter` 的 `session_id` 分支）
- Test: `tests/test_server.py`、`tests/test_orchestrator_pipeline.py`

**Interfaces:**
- Consumes: 无
- Produces: `EventQueueChannel.awaiting_answer: bool`（`ask()` 期间为 True）

- [ ] **Step 1: 写失败测试**

在 `tests/test_orchestrator_pipeline.py` 追加：

```python
@pytest.mark.asyncio
async def test_channel_awaiting_answer_flag_tracks_ask():
    """ask() 期间 awaiting_answer 为 True，返回后复位 —— 供 /voice/utter 判断会话是否被占用。
    awaiting_answer is True while ask() is pending and resets afterwards, so /voice/utter
    can tell whether the session is busy."""
    events: asyncio.Queue = asyncio.Queue()
    ch = EventQueueChannel(events, session_id="s1")
    assert ch.awaiting_answer is False
    t = asyncio.ensure_future(ch.ask("问题?"))
    await asyncio.wait_for(events.get(), timeout=1.0)
    assert ch.awaiting_answer is True
    ch.answer("回答")
    await asyncio.wait_for(t, timeout=1.0)
    assert ch.awaiting_answer is False
```

在 `tests/test_server.py` 追加：

```python
def test_voice_utter_rejected_while_session_awaiting_answer(client):
    """会话正阻塞在 ask() 时，新的 utter 必须被拒 —— 否则会新建 Session 覆盖注册表，
    把旧的 ask() 变成永久挂死的孤儿。A new utter must be rejected while the session is
    blocked in ask(); otherwise it would create a fresh Session, overwrite the registry,
    and orphan the old ask() forever."""
    import asyncio
    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Session

    session = Session(session_id="busy")
    ch = EventQueueChannel(asyncio.Queue(), "busy")
    ch.awaiting_answer = True
    session.channel = ch
    state.register(session, StopController())
    try:
        r = client.post("/api/voice/utter", json={"text": "新的指令", "session_id": "busy"})
        assert r.status_code == 409
        assert "等待回答" in r.json()["error"]
    finally:
        state.cleanup("busy")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_orchestrator_pipeline.py -q -k awaiting && python -m pytest tests/test_server.py -q -k awaiting`
Expected: FAIL — `AttributeError: 'EventQueueChannel' object has no attribute 'awaiting_answer'`

- [ ] **Step 3: 实现**

`core/orchestrator/pipeline.py` 的 `EventQueueChannel.__init__` 加：

```python
        # 是否正阻塞在 ask()：供 /voice/utter 判断该会话是否已被占用。
        # Whether an ask() is currently pending, so /voice/utter can tell the session is busy.
        self.awaiting_answer = False
```

`ask()` 改为：

```python
        async with self._ask_lock:
            await self.events.put(
                QuestionEvent(question=question, session_id=self.session_id,
                              kind=kind, options=options or []).emit()
            )
            self.awaiting_answer = True
            try:
                return await self.answers.get()
            finally:
                self.awaiting_answer = False
```

`core/api/voice.py` 的 `voice_utter`，在 `if isinstance(session_id, str) and session_id:` 分支的**最前面**加：

```python
        # 该会话正阻塞在 ask()：拒绝本次 utter。否则会新建 Session 覆盖注册表，
        # 旧的 ask() 将永久挂死（前端 runTurn 也会 abort 掉那条流）。
        # The session is blocked in ask(): reject this utter. Otherwise a fresh Session
        # would overwrite the registry and the old ask() would hang forever (the frontend's
        # runTurn would also abort that stream).
        busy = state.get_session(session_id)
        channel = getattr(busy, "channel", None) if busy else None
        if channel is not None and getattr(channel, "awaiting_answer", False):
            return JSONResponse(
                {"ok": False, "error": "该会话正在等待回答，请先作答或新建会话"},
                status_code=409,
            )
```

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add core/orchestrator/pipeline.py core/api/voice.py tests/
git commit -m "feat(API): /voice/utter 拒绝正阻塞在 ask() 的会话（409）

纵深防御：前端路由正确时走不到这里；它防的是前端出 bug 或有人直接打 API。
不加守卫时新建 Session 会覆盖注册表，使旧的 ask() 永久挂死。"
```

---

## Task 9: 全量验证 + 人工验证清单

**Files:**
- Modify: `README.md`（语音交互说明）

- [ ] **Step 1: 全量自动化验证**

Run: `python -m pytest tests/ -q && python -m mypy core/ server.py && cd web && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 2: 起服务（严格确认端口，避免跑旧进程）**

```bash
taskkill //F //FI "IMAGENAME eq python.exe" ; sleep 2
netstat -ano | grep ":8520.*LISTENING" || echo "端口空闲"
python main.py serve > /tmp/server.log 2>&1 &
sleep 7 && (grep -qa "10048" /tmp/server.log && echo "❌ 跑的是旧进程" || echo "✓ 绑定成功")
```

- [ ] **Step 3: 人工验证（**必须真实麦克风与扬声器**）**

按 spec 的脚本逐条执行并**如实记录结果**：

1. 发一条会触发提问的任务 → 播报结束后**直接开口**说答案 → 应被识别并作答
2. 同上但在播报后**保持沉默 8s** → 应进入待机（界面显示「待机中…」文案）
3. 待机态说「小逻小逻」→ 应回到**本题**续答，而不是开新一轮
4. 让助手播报一段**含「小逻小逻」**的文本 → 不应自触发唤醒
5. 用界面按钮作答（不经语音）→ 行为不变（回归）

> **这一节无法用自动化替代**：Vosk 是浏览器 WASM 引擎，Vitest 无法驱动真实音频；
> 扬声器时序与新状态文案的真实观感也测不到。若某项环境不具备（如无可用麦克风），
> **如实标注为「未验证」**，不得写成通过。

- [ ] **Step 4: 同步 README**

「语音助手使用」节补：提问后可直接语音作答、无应答进待机、再唤醒续答本题；以及播报期间会暂停监听。

- [ ] **Step 5: 提交并推送**

```bash
git add README.md
git commit -m "docs: 语音作答/待机续答的说明"
git push origin main
```

---

## 完成标准

- [ ] `python -m pytest tests/ -q` 全绿；`python -m mypy core/ server.py` 无问题
- [ ] `cd web && npm test` 全绿；`npm run build` 通过
- [ ] `AsstState` 的 6 处同步点全部核对（其中 4 处不报编译错，必须人工看）
- [ ] `matchOption` 的对抗用例（子串/归一化）全绿 —— 安全边界未被放宽
- [ ] 人工验证 5 条**逐条记录结果**；不具备条件的标注「未验证」，不得含糊

---

## 验证记录（2026-09-13 实施完成后填写）

### ✅ 已自动验证

| 项 | 结果 |
|---|---|
| 后端全量 `pytest` | **352 passed**（实施前 347） |
| 前端全量 `vitest` | **113 passed**（实施前 103） |
| `mypy core/ server.py` | 无问题（81 文件） |
| `npm run build`（vue-tsc + vite） | 通过 |
| `generated.ts` 与后端 schema 同步 | 一致 |
| `matchOption` 安全边界 | 变异检验：改子串匹配 → 2 个对抗用例失败 |
| `speaking` 代际计数 | 变异检验：去掉代际 → 迟到 onend 用例失败 |
| `handleTranscript` 分流 | 变异检验：去掉分流 → 2 个核心用例失败 |
| 门控 stop/start | 变异检验：分别移除 → 对应用例失败 |
| 迁移表 `nextState` | 7 个用例穷尽覆盖 |
| `/voice/utter` 409 守卫 | 变异检验：移除守卫 → 用例失败 |
| `STATE_VISUALS` 编译强制 | 删 `standby` 项 → `TS2741` |
| **配置到达前端** | `/api/config` 返回 `vad.answer_timeout_ms=8000`（这正是「双份 VadConfig」未同步时会被静默过滤掉的值） |
| **唤醒启动链路未回归** | Playwright 启动唤醒引擎 → 进入 `fx-listening`、界面显示「聆听中…」、0 console 报错 |

### ❌ 未验证（环境不具备，非「通过」）

以下 5 项**需要真实麦克风拾音与扬声器输出**，本环境无法完成 —— 没有可发声的输入源，
也无法听到播报。本机虽有音频设备（Realtek / USB Audio / NVIDIA），但无法由我对着麦克风说话。

| # | 项 | 状态 |
|---|---|---|
| 1 | 播报结束后直接开口说答案 → 被识别并作答 | **未验证** |
| 2 | 播报后沉默 8s → 进入待机（界面显示待机文案） | **未验证** |
| 3 | 待机态说「小逻小逻」→ 回到本题续答而非开新一轮 | **未验证** |
| 4 | 助手播报含「小逻小逻」的文本 → 不自触发唤醒 | **未验证** |
| 5 | 界面按钮作答行为不变 | 由 P4 的既有自动化用例覆盖（非人工项） |

**因此 P6 的结论是「自动化全绿 + 运行时冒烟通过，但语音链路的端到端行为未经验证」。**
不得据此宣称语音作答功能可用。需在有麦克风与扬声器的环境下按上表逐条人工验证。
