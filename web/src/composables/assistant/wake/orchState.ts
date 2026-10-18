// 拆分自 wakeOrchestrator.ts（重构：纯移动 + 状态收敛到 orchState.st，无行为变化）。
// Split from wakeOrchestrator.ts (pure move; mutable state consolidated into orchState.st).

import type { Ref } from 'vue'
import { nextState } from '../wakeFsm'
import {
  state, statusLine, vadConfig, pendingQuestion, wakeEnabled, currentSessionId, callActive,
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
  /** 退出通话会话（静止超时自动退通话用；useWakeWord 注入的完整 api 自带，测试桩可缺省）。
   *  Exit the call session (used by the idle-timeout auto-exit; the full api injected by
   *  useWakeWord carries it, test doubles may omit it). */
  callStop?(): Promise<unknown>
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
  /** 静待中裸唤醒 → 进入通话聆听（useWakeWord 注入 callMode.enterCallFromWake；
   *  返回 false/缺省时调用方回退指令窗语义，不丢唤醒）。
   *  Bare wake in standby → enter call listening (useWakeWord injects
   *  callMode.enterCallFromWake; a false/absent return falls back to the command-window
   *  semantics so the wake is never lost). */
  enterCall?(): Promise<boolean>
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
  idleTimer: ReturnType<typeof setTimeout> | null
  idleDeadline: number
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
  idleTimer: null,
  idleDeadline: 0,
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

const TRANSCRIBABLE: AsstState[] = ['listening', 'awaiting_answer', 'recording', 'followup', 'standby']

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

// ── 聆听空闲超时（vad.listen_idle_s）→ 静待 ──
// 口径：只有「实质输入」重置截止时间（runTurn 入口 / sendAnswer 成功 / 回合 done），
// 裸唤醒往返指令窗、空转写、漏斗 miss 都不续命。定时器只在 listening 期间挂表：
// 中间态（thinking 等）到来时被 watches 的统一清理摘掉，回到 listening 按**剩余**
// 时间重挂 —— 长回合不会把计时"藏起来"。
// Listening idle timeout (vad.listen_idle_s) → standby. Only substantive input
// extends the deadline (runTurn entry / sendAnswer success / turn done); bare-wake
// excursions, empty transcripts and funnel misses never renew it. The timer only
// runs while listening: intermediate states drop it via the unified cleanup in
// watches, and re-entering listening re-schedules the **remaining** time — a long
// turn cannot hide the clock.

/** 聆听空闲时长（毫秒；0=永不超时）。Listening idle timeout in ms (0 = never). */
export function listenIdleMs(): number {
  const s = (vadConfig as { listen_idle_s?: number }).listen_idle_s
  return s && s > 0 ? s * 1000 : 0
}

export function clearIdleTimer() {
  if (st.idleTimer) { clearTimeout(st.idleTimer); st.idleTimer = null }
}

/** 按剩余时间武装空闲定时器（listen_idle_s=0 关闭）。
 *  Arm the idle timer with the remaining time (listen_idle_s=0 disables it).
 *
 *  语义（用户口径，无条件）：**静止 listen_idle_s 秒 → 静待** —— 通话中同样生效，
 *  到点自动干净退出通话（漏斗停、麦保持）再落静待；截止时间已过/未设时刷新为
 *  「此刻 + N」（上一个聆听会话的窗口已耗尽，新开会话给完整窗口，不瞬移静待）。
 *  Semantics (user rule, unconditional): **silent for listen_idle_s → standby** — it
 *  applies mid-call too: on expiry the call is cleanly exited (funnel stops, mic stays)
 *  and standby is entered. A missing/past deadline refreshes to "now + N" (the previous
 *  listening session's window is used up; a fresh session gets a full window instead of
 *  an instant standby).
 */
export function armIdleTimer() {
  clearIdleTimer()
  const total = listenIdleMs()
  if (!total) return
  if (!st.idleDeadline || st.idleDeadline <= Date.now()) st.idleDeadline = Date.now() + total
  const remain = st.idleDeadline - Date.now()
  const fire = () => {
    st.idleTimer = null
    if (state.value !== 'listening') return          // 陈旧触发（状态已走）。Stale fire.
    if (Date.now() < st.idleDeadline) { armIdleTimer(); return }   // 被续期过。Extended meanwhile.
    if (callActive.value) {
      // 静止超时无条件生效：干净退出通话（callActive 落 false → 段不再进漏斗、
      // 唤醒判定接管；后端通话会话由 callStop 立即关闭，best-effort）。
      // Unconditional idle timeout: exit the call cleanly (callActive=false → segments
      // leave the funnel and wake judging takes over; the backend call session closes
      // via callStop, best-effort).
      callActive.value = false
      wakeEnabled.value = true   // 静待的唤醒生命周期需要（done/播报回落都 gate 它）
      void st.deps?.api.callStop?.()?.catch?.(() => { /* 会话服务端 5 分钟自过期兜底 */ })
    }
    state.value = 'standby'
    statusLine.value = ''
    console.log('[wake] 聆听静止超时，转入静待（本地 KWS 侦听保持）')
  }
  st.idleTimer = setTimeout(fire, Math.max(0, remain))
}

/** 实质输入重置截止时间（当前在聆听则按新截止重挂表）。
 *  Substantive input resets the deadline (re-scheduling the timer when listening now). */
export function resetIdleDeadline() {
  const total = listenIdleMs()
  if (!total) return
  st.idleDeadline = Date.now() + total
  if (state.value === 'listening') armIdleTimer()
}

/**
 * 静待中的裸唤醒 → 通话聆听中（用户状态图：唤醒后进入持续聆听，漏斗接管判定）。
 * 成功：提示音 + 进通话（state/listening+callActive），返回 true —— 调用方直接 return；
 * 非静待态 / 未注入 enterCall / 启动失败：返回 false，调用方回退指令窗语义（不丢唤醒）。
 *
 * Bare wake in standby → call listening (user state diagram: after the wake word the
 * chain enters continuous listening, the funnel takes over judging). Success: chime +
 * call entered (listening + callActive), returns true — the caller returns right away;
 * not-standby / enterCall absent / startup failure: returns false and the caller falls
 * back to the command-window semantics (the wake is never lost).
 */
export async function tryEnterCallFromStandby(): Promise<boolean> {
  // 唤醒前静止态有两个：静待（电源开的正规落点）与 listening（徽章/起始页开的语音、
  // 回合结束后回落）。两者都不是通话中的中间态（通话中的段走漏斗分支，到不了这里），
  // 裸唤醒都应进通话 —— 只认 standby 会让 listening 一路回退指令窗（录音中…）。
  // Two pre-wake rest states exist: standby (the canonical power-on landing) and
  // `listening` (badge/start-page power-on, post-turn fallback). Neither is an in-call
  // intermediate (call segments take the funnel branch and never reach here), so a bare
  // wake must enter the call from both — accepting only standby sent `listening` into
  // the command window (the 「录音中…」 ring).
  if (state.value !== 'standby' && state.value !== 'listening') return false
  if (!st.deps?.enterCall) return false
  try {
    if (!(await st.deps.enterCall())) return false
    playBeep()
    return true
  } catch {
    return false
  }
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
