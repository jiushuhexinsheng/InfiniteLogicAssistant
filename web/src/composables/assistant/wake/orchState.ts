// 拆分自 wakeOrchestrator.ts（重构：纯移动 + 状态收敛到 orchState.st，无行为变化）。
// Split from wakeOrchestrator.ts (pure move; mutable state consolidated into orchState.st).

import type { Ref } from 'vue'
import { nextState } from '../wakeFsm'
import {
  state, statusLine, vadConfig, pendingQuestion, wakeEnabled, currentSessionId,
} from '../store'
import type { AsstState, PendingQuestion } from '../store'
import type { SegmentRecorder } from '../useSegmentRecorder'
import type { WakeProvider } from './types'
import type { BargeInMonitor } from '../bargeIn'

// ── 可注入依赖（由 useWakeWord.ts 注入）──

/** API 客户端（wakeCheck + wakeDetect + transcribe）。API client (wakeCheck + wakeDetect + transcribe). */
interface OrchestratorApi {
  /** 本地 KWS 快检：仅判定有没有唤醒词（毫秒级、零云端）。Local KWS quick check. */
  wakeCheck(blob: Blob): Promise<{ ok?: boolean; hit?: boolean; bypass?: boolean }>
  wakeDetect(blob: Blob, opts?: { mode?: string }): Promise<{ ok?: boolean; matched?: boolean; command?: string; text?: string }>
  transcribe(blob: Blob): Promise<{ ok?: boolean; text?: string }>
  /** 通话模式段落漏斗（Task 12 起接线；可选以保持既有测试假件兼容）。Call-mode segment funnel (wired in Task 12; optional so existing test doubles stay valid). */
  callSegment?(blob: Blob, meta: { tabFocused: boolean; inOpenWindow: boolean }): Promise<{ ok?: boolean; hit?: boolean; text?: string; stage?: string; reason?: string }>
  /** 停止任务并弃掉待答问题（T1 stop 端点毒丸；可选以保持既有测试假件兼容）。Stop the task and abandon the pending question (the T1 stop-endpoint poison pill; optional so existing test doubles stay valid). */
  stopTask?(sid: string): Promise<unknown>
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

/** 编排器全部模块级可变状态（单一实例，各拆分模块共享同一引用）。
 *  All module-level mutable state (one instance shared by every split module). */
export const st: {
  deps: OrchestratorDeps | null
  segmenter: SegmentRecorder | null
  micStream: MediaStream | null
  awaitingCommand: boolean
  failures: number
  breakerTrippedAt: number
  lastUploadAt: number
  listenGen: number
  startingWake: boolean
  commandTimer: ReturnType<typeof setTimeout> | null
  resetTimer: ReturnType<typeof setTimeout> | null
  followupTimer: ReturnType<typeof setTimeout> | null
  echoGuardUntil: number
  turnToken: number
  currentChain: WakeProvider[]
  lastMode: string | null
  bargeMonitor: BargeInMonitor | null
} = {
  deps: null,
  segmenter: null,
  micStream: null,
  awaitingCommand: false,
  failures: 0,
  breakerTrippedAt: 0,
  lastUploadAt: 0,
  listenGen: 0,
  startingWake: false,
  commandTimer: null,
  resetTimer: null,
  followupTimer: null,
  echoGuardUntil: 0,
  turnToken: 0,
  currentChain: [],
  lastMode: null,
  bargeMonitor: null,
}

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
  st.deps = d
}

// ── 模块级私有常量 ──

const FAILURE_LIMIT = 3
/** 熔断后的冷静期：期间暂停上传，过后自动恢复一次试探（不再永久静默 ——
 *  断连是间歇性的，永久熔断会让用户以为唤醒彻底坏了，只能手动关开恢复）。
 *  Cooldown after tripping: uploads pause for this long, then one probe is allowed
 *  (no more permanent silence — disconnects are intermittent, and a permanent break
 *  makes wake look dead until manually toggled). */
const BREAKER_COOLDOWN_MS = 60_000
export const DONE_RESET_MS = 3000

// ── 定时器管理 ──

const TRANSCRIBABLE: AsstState[] = ['listening', 'awaiting_answer', 'recording', 'followup']

// ── 续聊窗口（docs/designs/03-A）──

/** 续聊窗口时长（毫秒，0=关闭）。Follow-up window length (ms; 0 = off). */
export function followupWindowMs(): number {
  const ms = (vadConfig as { followup_window_ms?: number }).followup_window_ms
  return ms && ms > 0 ? ms : 0
}

/** 武装（或重新武装）续聊窗口。Arm (or re-arm) the follow-up window. */
export function armFollowupTimer() {
  clearFollowupTimer()
  const ms = followupWindowMs()
  if (!ms) return
  st.followupTimer = setTimeout(() => {
    st.followupTimer = null
    if (state.value !== 'followup') return   // 陈旧定时器（状态已走）。Stale timer.
    state.value = nextState(state.value, 'followup_expire')
    statusLine.value = ''
  }, ms)
}

export function clearFollowupTimer() {
  if (st.followupTimer) { clearTimeout(st.followupTimer); st.followupTimer = null }
}

export function clearCommandTimer() {
  if (st.commandTimer) { clearTimeout(st.commandTimer); st.commandTimer = null }
}

export function clearWaitTimers() {
  clearCommandTimer()
}

/**
 * 弃题（待答期间命中唤醒词）：清问题卡 + stopTask 解除后端 ask() 阻塞（T1 毒丸），
 * 本地 SSE 保持活着等 done(cancelled)。state 回 **thinking** —— 回合实际仍在跑（等收束），
 * 且新指令必须满足 outbox 入队条件（thinking ∈ TURN_RUNNING），否则 awaiting_answer
 * 直连 utter 会撞该会话的 409 busy 检查。与 useChat.abandonQuestion 同语义
 * （DI 边界各持一份，互为参照）。
 *
 * Abandon (wake word hit while awaiting): clear the card + stopTask to unblock the
 * backend ask() (the T1 poison pill), keeping the local SSE alive awaiting
 * done(cancelled). State returns to **thinking** — the turn is genuinely still running
 * (awaiting wrap-up) and a new instruction must satisfy the outbox enqueue condition
 * (thinking ∈ TURN_RUNNING), lest a direct utter from awaiting_answer hit that
 * session's 409 busy check. Same semantics as useChat.abandonQuestion (one copy per
 * DI boundary; cross-referenced).
 */
export function abandonPendingQuestion(): void {
  if (!pendingQuestion.value) return
  pendingQuestion.value = null
  state.value = 'thinking'
  const sid = currentSessionId.value
  if (sid) void st.deps?.api.stopTask?.(sid)?.catch?.(() => { /* 尽力而为。Best effort. */ })
}

// 指令窗时长（毫秒）：只武装「裸唤醒后等指令」的短窗 —— 回答超时计时器
// （armAnswerTimer 家族）已随「取消限时回答」删除，回答永不限时。配置键保持
// answer_timeout_ms 不改名（改名会炸旧 config.yaml 校验），语义已收敛到指令窗。
// Command window length (ms): only arms the short "bare wake, awaiting the command"
// window — the answer-timeout timer family (armAnswerTimer) is gone with the unlimited
// answer window; answers are never timed out. The config key stays answer_timeout_ms
// (a rename would break old config.yaml validation); its semantics narrowed to the
// command window.
function commandWindowMs(): number {
  const ms = (vadConfig as { answer_timeout_ms?: number }).answer_timeout_ms
  return ms && ms > 0 ? ms : 8000
}

export function armCommandTimer() {
  clearCommandTimer()
  st.commandTimer = setTimeout(() => {
    st.commandTimer = null
    if (!st.awaitingCommand) return
    st.awaitingCommand = false
    statusLine.value = ''
    if (state.value === 'recording') state.value = wakeEnabled.value ? 'listening' : 'idle'
    console.log('[wake] 等指令超时，恢复唤醒判定')
  }, commandWindowMs())
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
export const ECHO_GUARD_MS = 1200

/** 播报刚结束的回声窗口内。Whether we are inside the post-playback echo window. */
export function inEchoGuard(): boolean {
  return Date.now() < st.echoGuardUntil
}

export function playBeep() {
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

export function beginTranscribe(): AsstState | null {
  if (!TRANSCRIBABLE.includes(state.value)) return null
  const prev = state.value
  state.value = 'transcribing'
  return prev
}

export function endTranscribe(prev: AsstState | null) {
  if (prev && state.value === 'transcribing') state.value = prev
}

// ── 熔断 ──

export function resetFailures() {
  if (st.failures === 0 && !st.breakerTrippedAt) return
  st.failures = 0
  st.breakerTrippedAt = 0
  console.log('[wake] 用户重启监听，失败计数已清零')
}

export function onUploadFailed() {
  st.failures++
  if (st.failures >= FAILURE_LIMIT) {
    st.breakerTrippedAt = Date.now()
    statusLine.value = '⚠️ 云端唤醒暂不可用（已连续失败 3 次），1 分钟后自动重试；关闭再开启唤醒可立即恢复'
    console.warn('[wake] 连续失败达阈值，暂停上传，1 分钟后自动试探恢复')
  }
}

/**
 * 熔断门：是否应放行一次上传。冷静期内拦截；冷静期过后清零计数放行试探。
 * Circuit-breaker gate: whether one upload may proceed. Blocks during the cooldown;
 * after it expires the counter resets and a probe is allowed.
 */
export function breakerAllows(): boolean {
  if (st.failures < FAILURE_LIMIT) return true
  if (Date.now() - st.breakerTrippedAt >= BREAKER_COOLDOWN_MS) {
    st.failures = 0
    st.breakerTrippedAt = 0
    statusLine.value = ''
    console.log('[wake] 熔断冷静期结束，恢复上传试探')
    return true
  }
  return false
}
/** 发送权令牌：谁先认领（+1）谁才能发指令/回答，检查与认领必须原子化（都在 await 之后
 *  的同一同步段里完成）。指令段消费、回答投递、提取命中、停止监听都会认领 ——
 *  任何在途的另一路在认领前醒来都会发现令牌已变而作废，杜绝「同一语音被双重执行」。
 *  Send-claim token: whoever claims (increments) first gets to fire the command/answer;
 *  the check-and-claim must be atomic (same synchronous stretch after the await).
 *  Command consumption, answer delivery, extraction hit, and stop all claim — any
 *  in-flight alternative waking up before the claim sees the token changed and drops,
 *  ruling out "the same utterance executed twice". */
// ── 模块级 watch（播报门控 + 待答定时器 + 回聆听）──

/** 停掉 barge-in 监控（幂等）。Stop the barge-in monitor (idempotent). */
export function stopBargeIn() {
  if (st.bargeMonitor) {
    st.bargeMonitor.stop()
    st.bargeMonitor = null
  }
}

/** 是否开启打断播报（vad.barge_in；默认关 = 旧版「播报期间停麦」行为）。
 *  Whether barge-in is enabled (vad.barge_in; off by default = legacy mic-off behaviour). */
export function bargeInEnabled(): boolean {
  return (vadConfig as { barge_in?: boolean }).barge_in === true
}
