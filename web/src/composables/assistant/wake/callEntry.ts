// 拆分自 orchState.ts：静待裸唤醒进通话、待答弃题两个入口动作。
// Split from orchState.ts: bare-wake call entry and pending-question abandonment.

import { state, pendingQuestion, currentSessionId } from '../store'
import { st } from './orchStore'
import { playBeep } from './gate'

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
