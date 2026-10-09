import { watch } from 'vue'
import { nextState } from '../wakeFsm'
import { state, statusLine, wakeEnabled, pendingQuestion, callActive, markTurnEnded, callBargeInEnabled, vadConfig } from '../store'
import { startBargeInMonitor, BARGE_IN_DURATION_MS } from '../bargeIn'
import { st, armFollowupTimer, clearFollowupTimer, followupWindowMs, stopBargeIn, bargeInEnabled, DONE_RESET_MS, ECHO_GUARD_MS } from './orchState'
import { ensureListening, stopListening } from './micControl'
// 拆分自 wakeOrchestrator.ts（重构：纯移动 + 状态收敛到 orchState.st，无行为变化）。
// Split from wakeOrchestrator.ts (pure move; mutable state consolidated into orchState.st).
let watchesRegistered = false

export function registerWatches() {
  if (watchesRegistered) return
  watchesRegistered = true

  watch(() => st.deps?.speaking.value, (isSpeaking) => {
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
      if (callBargeInEnabled(bargeInEnabled()) && st.deps?.stopSpeak) {
        const stopSpeak = st.deps.stopSpeak
        st.bargeMonitor = startBargeInMonitor({
          threshold: Math.max(0.02, ((vadConfig.silence_threshold ?? 0.02) * 2)),
          durationMs: BARGE_IN_DURATION_MS,
          onTrigger: () => {
            st.bargeMonitor = null  // 监控已自停。Monitor stopped itself.
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
    st.echoGuardUntil = Date.now() + ECHO_GUARD_MS
    if (callActive.value) markTurnEnded()   // 通话态：播报真正结束 → 开放窗口起点
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
    if (st.resetTimer) { clearTimeout(st.resetTimer); st.resetTimer = null }
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
    st.resetTimer = setTimeout(() => {
      st.resetTimer = null
      if (!wakeEnabled.value) return
      if (state.value === 'done' || state.value === 'error') state.value = 'listening'
    }, DONE_RESET_MS)
  })
}
