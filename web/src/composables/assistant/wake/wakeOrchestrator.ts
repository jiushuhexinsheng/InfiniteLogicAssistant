/**
 * 唤醒主编排模块。
 *
 * 管理麦克风流、VAD 分段录音、回退链检测、状态机转换、定时器和播报门控。
 * 从 `useWakeWord.ts` 提取核心逻辑，通过 `wakeChain` 委托给各 provider。
 *
 * **依赖注入**：`api` / `sendText` / `sendAnswer` / `speaking` 由 `useWakeWord.ts` 通过
 * `configureOrchestrator()` 注入，不在本模块直接导入 —— 这样测试只需 mock `useWakeWord`
 * 的导入路径即可控制这些依赖，不需要知道本模块的内部路径。
 *
 * Wake orchestrator module.
 * Manages the mic stream, VAD segmentation, fallback-chain detection, state-machine transitions,
 * timers, and playback gating.
 *
 * **Dependency injection**: `api` / `sendText` / `sendAnswer` / `speaking` are injected by
 * `useWakeWord.ts` via `configureOrchestrator()` rather than imported here — so tests only need
 * to mock `useWakeWord`'s import paths and do not need to know this module's internal paths.
 */

import { watch, type Ref } from 'vue'
import { nextState } from '../wakeFsm'
import {
  state, partialText, statusLine, wakeEnabled, vadConfig,
  pendingQuestion, failWake, wakeKeywords, wakeMode,
} from '../store'
import type { AsstState, PendingQuestion } from '../store'
import { createSegmentRecorder, type SegmentRecorder } from '../useSegmentRecorder'
import { matchOption } from '../answerMatch'
import { detectWake, enterWakeCooldown, isWakeCooldown } from '../wakeMatch'
import { getChain, detectInChain, getWebSpeechProvider, peekWebSpeechProvider, disposeAll } from './wakeChain'
import type { WakeProvider } from './types'
import { startBargeInMonitor, BARGE_IN_DURATION_MS, type BargeInMonitor } from '../bargeIn'

// ── 可注入依赖（由 useWakeWord.ts 注入）──

/** API 客户端（wakeCheck + wakeDetect + transcribe）。API client (wakeCheck + wakeDetect + transcribe). */
interface OrchestratorApi {
  /** 本地 KWS 快检：仅判定有没有唤醒词（毫秒级、零云端）。Local KWS quick check. */
  wakeCheck(blob: Blob): Promise<{ ok?: boolean; hit?: boolean; bypass?: boolean }>
  wakeDetect(blob: Blob, opts?: { mode?: string }): Promise<{ ok?: boolean; matched?: boolean; command?: string; text?: string }>
  transcribe(blob: Blob): Promise<{ ok?: boolean; text?: string }>
}

/** 可注入依赖集合。Injectable dependencies. */
interface OrchestratorDeps {
  api: OrchestratorApi
  sendText: (text: string) => void
  sendAnswer: (text: string, choice?: string, source?: string, question?: PendingQuestion | null) => Promise<void> | void
  speaking: Ref<boolean>
  /** 停止播报（barge-in 命中时掐断 TTS；由 useTts 注入，缺省无操作）。
   *  Stop playback (cut the TTS on a barge-in hit; injected by useTts, no-op if absent). */
  stopSpeak?: (reason?: 'ui' | 'new_turn' | 'barge_in') => void
}

let deps: OrchestratorDeps | null = null

/**
 * 注入编排器依赖。
 *
 * Configure orchestrator dependencies.
 *
 * 由 `useWakeWord.ts` 在模块加载时调用一次。
 * Called once by `useWakeWord.ts` at module load.
 *
 * @param d 依赖集合。The dependencies.
 */
export function configureOrchestrator(d: OrchestratorDeps) {
  deps = d
}

// ── 模块级私有状态 ──

let segmenter: SegmentRecorder | null = null
let micStream: MediaStream | null = null
let awaitingCommand = false
let failures = 0
const FAILURE_LIMIT = 3
/** 熔断后的冷静期：期间暂停上传，过后自动恢复一次试探（不再永久静默 ——
 *  断连是间歇性的，永久熔断会让用户以为唤醒彻底坏了，只能手动关开恢复）。
 *  Cooldown after tripping: uploads pause for this long, then one probe is allowed
 *  (no more permanent silence — disconnects are intermittent, and a permanent break
 *  makes wake look dead until manually toggled). */
const BREAKER_COOLDOWN_MS = 60_000
let breakerTrippedAt = 0
let lastUploadAt = 0
let listenGen = 0
let startingWake = false
let answerTimer: ReturnType<typeof setTimeout> | null = null
let commandTimer: ReturnType<typeof setTimeout> | null = null
let resetTimer: ReturnType<typeof setTimeout> | null = null
const DONE_RESET_MS = 3000
let currentChain: WakeProvider[] = []
let lastMode: string | null = null

// ── 定时器管理 ──

const TRANSCRIBABLE: AsstState[] = ['listening', 'standby', 'awaiting_answer', 'recording', 'followup']

function clearAnswerTimer() {
  if (answerTimer) { clearTimeout(answerTimer); answerTimer = null }
}

// ── 续聊窗口（docs/designs/03-A）──

/** 续聊窗口计时器（到期回聆听）。Follow-up window timer (expiry → listening). */
let followupTimer: ReturnType<typeof setTimeout> | null = null

/** 续聊窗口时长（毫秒，0=关闭）。Follow-up window length (ms; 0 = off). */
function followupWindowMs(): number {
  const ms = (vadConfig as { followup_window_ms?: number }).followup_window_ms
  return ms && ms > 0 ? ms : 0
}

/** 武装（或重新武装）续聊窗口。Arm (or re-arm) the follow-up window. */
function armFollowupTimer() {
  clearFollowupTimer()
  const ms = followupWindowMs()
  if (!ms) return
  followupTimer = setTimeout(() => {
    followupTimer = null
    if (state.value !== 'followup') return   // 陈旧定时器（状态已走）。Stale timer.
    state.value = nextState(state.value, 'followup_expire')
    statusLine.value = ''
  }, ms)
}

function clearFollowupTimer() {
  if (followupTimer) { clearTimeout(followupTimer); followupTimer = null }
}

function clearCommandTimer() {
  if (commandTimer) { clearTimeout(commandTimer); commandTimer = null }
}

function clearWaitTimers() {
  clearAnswerTimer()
  clearCommandTimer()
}

function answerTimeoutMs(): number {
  const ms = (vadConfig as { answer_timeout_ms?: number }).answer_timeout_ms
  return ms && ms > 0 ? ms : 8000
}

function armAnswerTimer() {
  clearAnswerTimer()
  answerTimer = setTimeout(() => {
    answerTimer = null
    if (!wakeEnabled.value) return
    const ns = nextState(state.value, 'answer_timeout')
    if (ns !== state.value) state.value = ns
  }, answerTimeoutMs())
}

function armCommandTimer() {
  clearCommandTimer()
  commandTimer = setTimeout(() => {
    commandTimer = null
    if (!awaitingCommand) return
    awaitingCommand = false
    statusLine.value = ''
    if (state.value === 'recording') state.value = wakeEnabled.value ? 'listening' : 'idle'
    console.log('[wake] 等指令超时，恢复唤醒判定')
  }, answerTimeoutMs())
}

// ── TTS 回声护栏 ──

/** 播报结束后的静默窗口（毫秒）：窗口内的音频段整体丢弃（唤醒判定与作答通道都不收）。
 *  TTS 结束 ≠ 喇叭静音 —— onend 之后仍有尾音/房间回声，而助手自称「衍衡」，
 *  拾到就会误唤醒 → 新回合 → 掐死待答问题 → 新回应 → 再回声，形成连锁循环
 *  （症状：问题没让我回答/一闪而过、重复执行好几遍、录音窗口反复冒出）。
 *  Silence window after playback ends (ms): segments inside it are dropped outright
 *  (neither wake judging nor the answer channel takes them). TTS end ≠ speaker silent —
 *  tail audio and room echo linger, and the assistant calls itself 衡衍: catching it
 *  false-wakes → a new turn kills the pending question → new response → echo again.
 */
const ECHO_GUARD_MS = 1200
let echoGuardUntil = 0

/** 播报刚结束的回声窗口内。Whether we are inside the post-playback echo window. */
function inEchoGuard(): boolean {
  return Date.now() < echoGuardUntil
}

function playBeep() {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain); gain.connect(ctx.destination)
    osc.type = 'sine'
    osc.frequency.setValueAtTime(800, ctx.currentTime)
    osc.frequency.linearRampToValueAtTime(1000, ctx.currentTime + 0.1)
    gain.gain.setValueAtTime(0.3, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.2)
    setTimeout(() => ctx.close().catch(() => {}), 500)
  } catch { /* mute */ }
}

// ── 识别中状态管理 ──

function beginTranscribe(): AsstState | null {
  if (!TRANSCRIBABLE.includes(state.value)) return null
  const prev = state.value
  state.value = 'transcribing'
  return prev
}

function endTranscribe(prev: AsstState | null) {
  if (prev && state.value === 'transcribing') state.value = prev
}

// ── 熔断 ──

function resetFailures() {
  if (failures === 0 && !breakerTrippedAt) return
  failures = 0
  breakerTrippedAt = 0
  console.log('[wake] 用户重启监听，失败计数已清零')
}

function onUploadFailed() {
  failures++
  if (failures >= FAILURE_LIMIT) {
    breakerTrippedAt = Date.now()
    statusLine.value = '⚠️ 云端唤醒暂不可用（已连续失败 3 次），1 分钟后自动重试；关闭再开启唤醒可立即恢复'
    console.warn('[wake] 连续失败达阈值，暂停上传，1 分钟后自动试探恢复')
  }
}

/**
 * 熔断门：是否应放行一次上传。冷静期内拦截；冷静期过后清零计数放行试探。
 * Circuit-breaker gate: whether one upload may proceed. Blocks during the cooldown;
 * after it expires the counter resets and a probe is allowed.
 */
function breakerAllows(): boolean {
  if (failures < FAILURE_LIMIT) return true
  if (Date.now() - breakerTrippedAt >= BREAKER_COOLDOWN_MS) {
    failures = 0
    breakerTrippedAt = 0
    statusLine.value = ''
    console.log('[wake] 熔断冷静期结束，恢复上传试探')
    return true
  }
  return false
}

// ── 云端转写 ──

async function transcribeSegment(blob: Blob): Promise<string> {
  const prev = beginTranscribe()
  try {
    const r = await deps!.api.transcribe(blob)
    return (r?.text || '').trim()
  } catch {
    onUploadFailed()
    return ''
  } finally {
    endTranscribe(prev)
  }
}

// ── 获取当前链（按模式） ──

function ensureChain(): WakeProvider[] {
  const mode = wakeMode.value
  if (mode !== lastMode) {
    currentChain = getChain(mode, deps!.api)
    lastMode = mode
  }
  return currentChain
}

// ── 处理一段音频（云端链路）──

/**
 * 处理一段音频：先看是不是在回答问题，否则做唤醒检测。
 *
 * Handle one audio segment: an answer first, wake detection otherwise.
 */
/** 段处理串行队列：VAD 可以背靠背出段，并发处理会交错穿过 await 空隙
 *  （两个段同时过「等指令中？」检查 → 双重触发/重复执行/重复录音）。
 *  公共入口 handleSegment 排队逐段执行，段与段不交叠。
 *  Serial segment queue: VAD can emit segments back-to-back; concurrent processing
 *  interleaves through the await gaps (two segments both pass the "awaiting command?"
 *  check → double fires / repeated execution / repeated prompts). The public
 *  handleSegment queues them so segments never interleave. */
let segmentChain: Promise<void> = Promise.resolve()

export function handleSegment(blob: Blob): Promise<void> {
  segmentChain = segmentChain
    .then(() => processSegment(blob))
    .catch((e) => console.warn('[wake] handleSegment error:', e))
  return segmentChain
}

async function processSegment(blob: Blob) {
  if (!deps) return

  // TTS 回声窗口内的段整体丢弃：尾音/回声既不能唤醒，也不能被当作对提问的回答
  // （否则助手自己的声音会「替你回答」，问题一闪而过 —— 没法回答/极短）。
  // Drop segments inside the post-playback echo window outright: tail/echo audio must
  // neither wake the assistant nor answer a pending question (otherwise the assistant's
  // own voice answers for you and the question flashes by).
  if (inEchoGuard()) return

  // ⚠️ 熔断只作用于唤醒检测路径，不阻断答案/指令通道 ——
  // 答案和指令走的是 api.transcribe（不同端点），与唤醒检测的 api.wakeDetect 无关。
  // wakeDetect 挂了但 transcribe 正常时，语音作答仍应可用。
  //
  // The circuit breaker only guards the wake-detection path; answer and command channels
  // are NOT blocked — they use api.transcribe (a different endpoint) from api.wakeDetect.
  // Voice answering must stay available when wakeDetect is down but transcribe works.

  const pq = pendingQuestion.value
  if (pq) {
    turnToken++                 // 作废在飞的尾随提取：本段被消费为回答，任何迟到提取都不得再发
    state.value = nextState(state.value, 'wake_detected')
    if (state.value === 'awaiting_answer') armAnswerTimer()
    const text = await transcribeSegment(blob)
    if (!text) return
    failures = 0
    const hit = matchOption(text, pq.options)
    clearAnswerTimer()          // 已作答：作废陈旧超时，免得 8 秒后把状态踢进待机
    // 传段落捕获的问题快照：云端转写数秒内 pendingQuestion 可能被清（流错误竞态），
    // sendAnswer 内部不得重读 store（read-after-await 会让 qid 丢失 → 问答分开）。
    // Pass the question snapshot captured at segment start: during the multi-second
    // ASR await pendingQuestion may be cleared (stream-error race), and sendAnswer
    // must not re-read the store (that read-after-await loses the qid → Q/A split).
    await deps.sendAnswer(hit ? '' : text, hit?.value, 'voice', pq)
    return
  }

  if (awaitingCommand) {
    const token = turnToken     // 领取发送权令牌（在 await 之前捕获）
    const text = await transcribeSegment(blob)
    if (token !== turnToken) return   // 期间已有更新的交互认领 → 本段作废
    if (text) {
      awaitingCommand = false
      clearCommandTimer()
      statusLine.value = ''
      if (state.value === 'recording') state.value = 'listening'
      failures = 0
      turnToken++             // 认领：作废在飞的尾随提取（原子于发送）
      enterWakeCooldown()
      deps.sendText(text)
    } else {
      armCommandTimer()
    }
    return
  }

  // ── 续聊窗口（docs/designs/03-A）：窗口内的段免唤醒直接当新指令 ──
  // 位置在 pendingQuestion/awaitingCommand 之后（作答与指令窗优先）、熔断/节流之前
  // （与答案/指令同走 api.transcribe 通道，唤醒熔断不适用）。转写文本先过唤醒词判定：
  // 说中唤醒词照常进指令窗/直接执行（窗口与唤醒语义兼容），否则整句即指令。
  //
  // Follow-up window (docs/designs/03-A): segments inside the window become fresh
  // instructions without the wake word. Placed after pendingQuestion/awaitingCommand
  // (answering and the command window win) and before breaker/throttle (it rides the
  // api.transcribe channel like answers/commands, so the wake breaker does not apply).
  // The transcript is still wake-word checked: a wake word opens the command window /
  // runs its command as usual (the window stays compatible with wake semantics);
  // otherwise the whole sentence is the instruction.
  if (state.value === 'followup') {
    const token = turnToken
    const text = await transcribeSegment(blob)
    if (token !== turnToken) return
    if (!text) { armFollowupTimer(); return }   // 空转写：窗口续期。Empty transcript: keep the window.
    failures = 0
    const r = detectWake(text, wakeKeywords.value)
    if (r.matched) {
      if (r.command) {
        turnToken++
        enterWakeCooldown()
        clearFollowupTimer()
        deps.sendText(r.command)
      } else {
        awaitingCommand = true
        statusLine.value = '已唤醒，请说指令…'
        state.value = 'recording'
        armCommandTimer()
      }
      return
    }
    turnToken++              // 认领：作废在飞的尾随提取。Claim: void in-flight extraction.
    clearFollowupTimer()     // 状态随 sendText → runTurn 走 thinking，计时器一并收（双保险）。
    deps.sendText(text)
    return
  }

  // 熔断：只阻断唤醒检测上传（答案/指令通道不受影响，见上方说明）；
  // 冷静期（60s）过后自动放行试探，不再永久静默。
  // Circuit break: only blocks wake-detection uploads (answer/command channels
  // unaffected); after the cooldown (60s) a probe is allowed — no permanent silence.
  if (!breakerAllows()) return

  const now = Date.now()
  if (now - lastUploadAt < vadConfig.upload_throttle_ms) return
  lastUploadAt = now

  const mode = wakeMode.value
  if (mode === 'webspeech') return

  // 唤醒冷却：刚发过指令/作答后的短窗口内不再判定唤醒词（防指令回声被当成新唤醒）。
  // 冷却此前只在 Web Speech 路径检查，云端/KWS 路径漏检 —— 武装了却从不生效。
  // Wake cooldown: no wake judging shortly after a command/answer was sent (a command's
  // own echo must not fire a fresh wake). The cooldown used to be checked only on the
  // Web Speech path — armed on all paths, enforced on one.
  if (isWakeCooldown()) return

  // ── 判定与提取分离（本地/auto）：KWS 快检先动作，指令提取后台跑 ──
  // 本地 KWS 毫秒级确认唤醒词 → 立即提示音 + 进入等指令窗口（动作先行，不等任何
  // 「二次确认」）；同一段里可能带的指令（「衍衡，查天气」）由后台 /voice/wake
  // 转写提取，提到就直接执行、提不到就保持窗口等你说。
  // cloud 模式跳过快检：上传 → ASR 文本判定 → 动作（云端说了算，慢是本性）。
  //
  // Verdict first, extraction later (local/auto): local KWS confirms the wake word
  // in milliseconds → immediate chime + command window (act now, no re-confirmation);
  // any command carried in the same clip is extracted in the background via
  // /voice/wake — if found it executes at once, otherwise the window stays open.
  // cloud mode skips the check: upload → ASR text verdict → act (the cloud decides,
  // and that is inherently slow).
  if (mode !== 'cloud') {
    let check: { ok?: boolean; hit?: boolean; bypass?: boolean }
    try {
      check = await deps.api.wakeCheck(blob)
    } catch {
      onUploadFailed()
      return
    }
    if (!check?.ok) {
      onUploadFailed()
      return
    }
    if (check.bypass) {
      // KWS 闸门不可用 → 回退完整路径（云端判定），不丢唤醒。
      // Gate unavailable → fall back to the full path (cloud judging); never lose the wake.
      await fullDetect(ensureChain(), blob)
      return
    }
    if (!check.hit) return   // 未命中：丢弃，不出本机、零成本
    failures = 0

    // ── 命中：立即动作 ──
    awaitingCommand = true
    statusLine.value = '已唤醒，请说指令…'
    if (state.value === 'listening' || state.value === 'standby') state.value = 'recording'
    playBeep()
    armCommandTimer()
    void extractTrailingCommand(blob, mode)   // 不 await：后台提取尾随指令
    return
  }

  await fullDetect(ensureChain(), blob)
}

/** 发送权令牌：谁先认领（+1）谁才能发指令/回答，检查与认领必须原子化（都在 await 之后
 *  的同一同步段里完成）。指令段消费、回答投递、提取命中、停止监听都会认领 ——
 *  任何在途的另一路在认领前醒来都会发现令牌已变而作废，杜绝「同一语音被双重执行」。
 *  Send-claim token: whoever claims (increments) first gets to fire the command/answer;
 *  the check-and-claim must be atomic (same synchronous stretch after the await).
 *  Command consumption, answer delivery, extraction hit, and stop all claim — any
 *  in-flight alternative waking up before the claim sees the token changed and drops,
 *  ruling out "the same utterance executed twice". */
let turnToken = 0

/**
 * 后台提取同一段音频里尾随唤醒词的指令（一句话场景「衍衡，查天气」）。
 * 提到 → 直接执行并收回指令窗口；提不到 → 窗口保持，等操作者说指令。
 * 失败不打断已开的窗口（两步式照常可用）。
 *
 * Background-extract the command trailing the wake word in the same clip (the
 * one-sentence case "衍衡，查天气"). Found → execute at once and retract the
 * window; not found → keep the window open. Failures never disturb the open
 * window (the two-step flow keeps working).
 */
async function extractTrailingCommand(blob: Blob, mode: string) {
  if (!deps) return
  const token = turnToken          // await 之前捕获令牌
  try {
    const r = await deps.api.wakeDetect(blob, { mode })
    if (token !== turnToken) return     // 已被更新的交互认领 → 丢弃（防双重执行）
    if (r?.ok && r.command) {
      turnToken++                     // 认领发送权（原子于下面的 sendText）
      awaitingCommand = false
      clearCommandTimer()
      statusLine.value = ''
      if (state.value === 'recording') state.value = 'listening'
      enterWakeCooldown()
      deps.sendText(r.command)
    }
  } catch {
    /* 提取失败不影响已开的指令窗口 */
  }
}

/** 完整判定路径（cloud 模式 / KWS 旁路回退）：上传 → ASR 文本判定 → 动作。
 *  Full judging path (cloud mode / KWS-bypass fallback): upload → ASR text verdict → act. */
async function fullDetect(chain: ReturnType<typeof ensureChain>, blob: Blob) {
  if (!deps) return
  if (chain.length === 0) return
  const prev = beginTranscribe()
  let result: { matched: boolean; command: string }
  try {
    result = await detectInChain(chain, blob, wakeKeywords.value)
  } catch {
    onUploadFailed()
    return
  } finally {
    endTranscribe(prev)
  }

  if (!result.matched) return
  failures = 0
  statusLine.value = ''

  if (result.command) {
    turnToken++                 // 认领发送权
    enterWakeCooldown()
    deps.sendText(result.command)
    return
  }

  awaitingCommand = true
  statusLine.value = '已唤醒，请说指令…'
  if (state.value === 'listening' || state.value === 'standby') state.value = 'recording'
  playBeep()
  armCommandTimer()
}

// ── 处理本地识别结果（Web Speech API 路径）──

export function handleLocalResult(text: string) {
  if (!deps) return
  const trimmed = text.trim()
  if (!trimmed) return

  const pq = pendingQuestion.value
  if (pq) {
    turnToken++                 // 认领：作废在飞提取
    state.value = nextState(state.value, 'wake_detected')
    if (state.value === 'awaiting_answer') armAnswerTimer()
    const hit = matchOption(trimmed, pq.options)
    clearAnswerTimer()
    // 同步路径也传快照（与云端转写路径一致的绑定语义）。Snapshot on the sync path too (same binding semantics as the ASR path).
    deps.sendAnswer(hit ? '' : trimmed, hit?.value, 'voice', pq)
    return
  }

  if (awaitingCommand) {
    awaitingCommand = false
    clearCommandTimer()
    statusLine.value = ''
    if (state.value === 'recording') state.value = 'listening'
    turnToken++             // 认领发送权
    enterWakeCooldown()
    deps.sendText(trimmed)
    return
  }

  // 续聊窗口（webspeech 路径，docs/designs/03-A）：未命中唤醒词的整句即指令；
  // 命中则照常进指令窗/执行（与云端路径同语义）。
  // Follow-up window (webspeech path, docs/designs/03-A): a non-wake sentence is the
  // instruction itself; a hit opens the command window / runs as usual (same semantics
  // as the cloud path).
  if (state.value === 'followup') {
    const rf = detectWake(trimmed, wakeKeywords.value)
    if (rf.matched) {
      if (rf.command) {
        turnToken++
        enterWakeCooldown()
        clearFollowupTimer()
        deps.sendText(rf.command)
      } else {
        awaitingCommand = true
        statusLine.value = '已唤醒，请说指令…'
        state.value = 'recording'
        armCommandTimer()
      }
      return
    }
    turnToken++
    clearFollowupTimer()
    deps.sendText(trimmed)
    return
  }

  const r = detectWake(trimmed, wakeKeywords.value)
  if (!r.matched) return
  if (r.command) { turnToken++; enterWakeCooldown(); deps.sendText(r.command); return }

  awaitingCommand = true
  statusLine.value = '已唤醒，请说指令…'
  if (state.value === 'listening' || state.value === 'standby') state.value = 'recording'
  playBeep()
  armCommandTimer()
}

// ── 分段录音器 ──

function startSegmenter() {
  if (!micStream) return
  segmenter = createSegmentRecorder(micStream, {
    speechThreshold: vadConfig.silence_threshold,
    silenceMs: vadConfig.silence_duration_ms,
    minSpeechMs: vadConfig.min_speech_ms,
    maxMs: vadConfig.max_duration_ms,
    onSegment: (b) => {
      void handleSegment(b).catch((e) => console.warn('[wake] handleSegment error:', e))
    },
  })
  segmenter.start()
}

// ── 停止监听 ──

export function stopListening() {
  listenGen++
  awaitingCommand = false
  clearWaitTimers()
  if (state.value === 'recording') state.value = wakeEnabled.value ? 'listening' : 'idle'

  const wsp = peekWebSpeechProvider()
  if (wsp?.isRunning()) wsp.stop()

  if (segmenter) {
    try { segmenter.stop() } catch (e) { console.error('[wake] segmenter stop error:', e) }
    segmenter = null
  }
  if (micStream) {
    try { micStream.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    micStream = null
  }
}

// ── 取流 ──

type AcquireOutcome = 'ok' | 'mic-error' | 'aborted'

async function acquireAndStart(): Promise<AcquireOutcome> {
  const mode = wakeMode.value

  if (mode === 'webspeech') {
    const wsp = getWebSpeechProvider()
    if (wsp.isRunning()) return 'ok'
    if (!wsp.isAvailable()) {
      statusLine.value = '⚠️ 当前浏览器不支持 Web Speech API，请切换到其他模式'
      return 'mic-error'
    }
    const started = wsp.start((text, isFinal) => {
      // 中间结果显示到 partialText（悬浮球可以看到正在听的内容）；最终结果清空并处理
      // Interim results shown in partialText (the ball shows what is being heard); final results clear and process
      partialText.value = isFinal ? '' : text
      if (isFinal) handleLocalResult(text)
    })
    if (!started) {
      statusLine.value = '⚠️ Web Speech API 启动失败'
      return 'mic-error'
    }
    return 'ok'
  }

  if (segmenter) return 'ok'
  const gen = listenGen
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
  } catch (e) {
    console.warn('[wake] getUserMedia failed:', e)
    statusLine.value = describeMicError(e)
    return 'mic-error'
  }
  if (gen !== listenGen) {
    try { stream.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    return 'aborted'
  }
  if (segmenter) {
    try { stream.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    return 'ok'
  }
  micStream = stream
  try {
    startSegmenter()
  } catch (e) {
    console.error('[wake] segmenter start failed:', e)
    statusLine.value = '唤醒启动失败，请重试'
    stopListening()
    return 'mic-error'
  }
  return 'ok'
}

async function ensureListening(): Promise<boolean> {
  if (!wakeEnabled.value) return false
  return (await acquireAndStart()) === 'ok'
}

// ── 麦克风错误描述 ──

export function describeMicError(e: any): string {
  const name = e?.name || ''
  switch (name) {
    case 'NotFoundError':
    case 'DevicesNotFoundError':
    case 'OverconstrainedError':
      return '未检测到可用麦克风，请检查麦克风连接或系统录音设备设置'
    case 'NotAllowedError':
    case 'PermissionDeniedError':
    case 'SecurityError':
      return '麦克风权限被拒绝，请点击地址栏🔒图标允许麦克风后重试'
    case 'NotReadableError':
    case 'TrackStartError':
    case 'AbortError':
      return '麦克风被其他程序占用或不可读，请关闭占用程序后重试'
    default: {
      const msg = typeof e?.message === 'string' ? e.message.trim() : ''
      return '麦克风访问失败：' + (msg || name || '未知错误')
    }
  }
}

// ── 开启/关闭唤醒 ──

export async function toggleWake() {
  console.log('[wake] toggleWake called, current state:', state.value)
  statusLine.value = ''
  resetFailures()

  // followup 与 done/error 同属「回合刚结束」窗口：录音器可能还活着 → acquireAndStart
  // 复用（与 done 窗口单击的既有语义一致），不重建。
  // followup is another "turn just ended" window alongside done/error: the recorder may
  // still be live → acquireAndStart reuses it (same semantics as a click in the done
  // window); no rebuild.
  if (state.value === 'idle' || state.value === 'done' || state.value === 'error'
      || state.value === 'followup') {
    if (startingWake) {
      console.log('[wake] enable already in flight, ignoring')
      return
    }
    startingWake = true
    try {
      statusLine.value = '正在启动唤醒...'

      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        const mics = devices.filter((d) => d.kind === 'audioinput')
        if (mics.length === 0) {
          console.warn('[wake] no audioinput device found')
          failWake('系统未检测到麦克风设备，请连接/启用麦克风后重试')
          return
        }
      } catch (e) {
        console.warn('[wake] enumerateDevices fail:', e)
      }

      const outcome = await acquireAndStart()
      if (outcome !== 'ok') {
        if (outcome === 'aborted') statusLine.value = '唤醒启动被打断，请再点一次'
        else failWake(statusLine.value || '麦克风启动失败，请检查系统/浏览器麦克风权限')
        return
      }
      wakeEnabled.value = true
      state.value = 'listening'
      statusLine.value = ''
      console.log('[wake] listening started!')
    } finally {
      startingWake = false
    }
  } else {
    console.log('[wake] stopping...')
    stopListening()
    wakeEnabled.value = false
    state.value = 'idle'
    partialText.value = ''
    statusLine.value = ''
  }
}

// ── 停止（页面销毁时调用）──

export function stopWake() {
  turnToken++          // 停止监听 → 作废在飞的尾随提取（停止后不得再发指令）
  stopBargeIn()
  stopListening()
  disposeAll()
}

// ── 模块级 watch（播报门控 + 待答定时器 + 回聆听）──

/** barge-in 监控句柄（播报期间的独立监听流，docs/designs/02 批3）。
 *  Barge-in monitor handle (the independent listening stream during playback). */
let bargeMonitor: BargeInMonitor | null = null

/** 停掉 barge-in 监控（幂等）。Stop the barge-in monitor (idempotent). */
function stopBargeIn() {
  if (bargeMonitor) {
    bargeMonitor.stop()
    bargeMonitor = null
  }
}

/** 是否开启打断播报（vad.barge_in；默认关 = 旧版「播报期间停麦」行为）。
 *  Whether barge-in is enabled (vad.barge_in; off by default = legacy mic-off behaviour). */
function bargeInEnabled(): boolean {
  return (vadConfig as { barge_in?: boolean }).barge_in === true
}

let watchesRegistered = false

export function registerWatches() {
  if (watchesRegistered) return
  watchesRegistered = true

  watch(() => deps?.speaking.value, (isSpeaking) => {
    if (isSpeaking) {
      // 段录音器始终停（喇叭声不得进唤醒/作答分流）；barge_in 开启时另起一条
      // 独立能量检测流，连续超阈（silence_threshold×2、400ms）即掐断播报。
      // 取流失败静默降级为纯停麦 —— 功能不可用不致坏。
      // The segment recorder always stops (speaker audio must not reach wake/answer
      // routing); with barge_in on, a separate energy-detection stream cuts playback
      // on sustained speech (silence_threshold × 2 for 400ms). A stream failure
      // degrades silently to plain mic-off — unavailable never breaks.
      stopBargeIn()
      stopListening()
      if (bargeInEnabled() && deps?.stopSpeak) {
        const stopSpeak = deps.stopSpeak
        bargeMonitor = startBargeInMonitor({
          threshold: Math.max(0.02, ((vadConfig.silence_threshold ?? 0.02) * 2)),
          durationMs: BARGE_IN_DURATION_MS,
          onTrigger: () => {
            bargeMonitor = null  // 监控已自停。Monitor stopped itself.
            stopSpeak('barge_in')
          },
          onFail: (err) => console.warn('[Wake] barge-in 监控启动失败，回退为播报期间停麦:', err),
        })
      }
      return
    }
    // 播报结束（含被 barge-in 掐断）→ 收监控 + 回声护栏窗口：窗口内的段丢弃
    // （喇叭尾音/回声不得唤醒或代答；barge-in 触发后的余响同样被这 1.2s 拦住）。
    // Playback ended (including a barge-in cut) → stop the monitor and arm the echo
    // guard: segments inside the window are dropped (speaker tail/echo must neither
    // wake nor answer; a barge-in's residual audio is caught by the same 1.2s).
    stopBargeIn()
    echoGuardUntil = Date.now() + ECHO_GUARD_MS
    // 续聊窗口从「播报真正结束」起重新计满（docs/designs/03-A：窗口 = 播报完后的 N 毫秒，
    // 而不是 done 事件到达时）；回声护栏 1.2s 仍在前面挡尾音。
    // Re-arm the follow-up window from actual end-of-playback (docs/designs/03-A: the
    // window is N ms *after* playback ends, not from the done event); the 1.2s echo
    // guard still sits in front.
    if (state.value === 'followup') armFollowupTimer()
    const q = pendingQuestion.value
    if (q) {
      const ns = nextState(state.value, 'question_ready')
      if (ns !== 'awaiting_answer') return
      state.value = ns
      void ensureListening()
      return
    }
    if (wakeEnabled.value) void ensureListening()
  })

  watch(state, (s) => {
    if (s === 'awaiting_answer') armAnswerTimer()
    else clearAnswerTimer()
  })

  watch(state, (s) => {
    if (resetTimer) { clearTimeout(resetTimer); resetTimer = null }
    clearFollowupTimer()
    // 续聊窗口态：武装到期计时（到点回聆听）。
    // Follow-up state: arm the expiry timer (→ listening).
    if (s === 'followup') {
      statusLine.value = ''
      armFollowupTimer()
      return
    }
    if (s !== 'done' && s !== 'error') return
    // 回合结束 → 优先开续聊窗口（docs/designs/03-A）；窗口关闭（0）或唤醒未开时
    // 回落旧版「3 秒后回聆听」。
    // Turn ended → prefer opening the follow-up window (docs/designs/03-A); with the
    // window off (0) or wake disabled, fall back to the legacy "listening after 3s".
    if (followupWindowMs() > 0 && wakeEnabled.value) {
      const ns = nextState(s, 'followup_open')
      if (ns === 'followup') {
        state.value = ns
        return
      }
    }
    resetTimer = setTimeout(() => {
      resetTimer = null
      if (!wakeEnabled.value) return
      if (state.value === 'done' || state.value === 'error') state.value = 'listening'
    }, DONE_RESET_MS)
  })
}