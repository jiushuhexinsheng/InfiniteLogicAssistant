// 拆分自 orchState.ts：续聊窗口、指令窗与聆听空闲三族计时器。
// Split from orchState.ts: follow-up window, command window and listening-idle timers.

import { nextState } from '../wakeFsm'
import {
  state, statusLine, vadConfig, wakeEnabled, callActive, callId,
} from '../store'
import { st } from './orchStore'
import { syncStreamGate } from './gate'

export const DONE_RESET_MS = 3000

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
      const id = callId.value
      callId.value = ''
      void st.deps?.api.callStop?.(id ? { call_id: id } : undefined)
        ?.catch?.(() => { /* 会话服务端 5 分钟自过期兜底 */ })
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
    syncStreamGate()   // 指令窗关闭 → 回到 wake 闸门。Window closed → back to the wake gate.
    console.log('[wake] 等指令超时，恢复唤醒判定')
  }, commandWindowMs())
}
