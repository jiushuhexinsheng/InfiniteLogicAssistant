import { state, statusLine, pendingQuestion, wakeKeywords, callActive } from '../store'
import { matchOption } from '../answerMatch'
import { detectWake, enterWakeCooldown } from '../wakeMatch'
import { st, abandonPendingQuestion, clearCommandTimer, armCommandTimer, clearFollowupTimer, playBeep } from './orchState'
// 拆分自 wakeOrchestrator.ts（重构：纯移动 + 状态收敛到 orchState.st，无行为变化）。
// Split from wakeOrchestrator.ts (pure move; mutable state consolidated into orchState.st).
// ── 处理本地识别结果（Web Speech API 路径）──

export function handleLocalResult(text: string) {
  if (!st.deps) return
  const trimmed = text.trim()
  if (!trimmed) return

  const pq = pendingQuestion.value
  if (pq) {
    st.turnToken++                 // 认领：作废在飞提取
    // 待答先判唤醒词（与云端转写路径同语义：命中弃题开新轮，未命中照旧作答）。
    // Wake check first while awaiting (same semantics as the ASR path: a hit abandons
    // and starts a fresh turn, a miss answers as before).
    const wake = detectWake(trimmed, wakeKeywords.value)
    if (wake.matched) {
      abandonPendingQuestion()
      if (wake.command) {
        st.turnToken++
        enterWakeCooldown()
        st.deps.sendText(wake.command)
      } else {
        st.awaitingCommand = true
        statusLine.value = '已唤醒，请说指令…'
        state.value = 'recording'
        armCommandTimer()
      }
      return
    }
    const hit = matchOption(trimmed, pq.options)
    // 同步路径也传快照（与云端转写路径一致的绑定语义）。Snapshot on the sync path too (same binding semantics as the ASR path).
    st.deps.sendAnswer(hit ? '' : trimmed, hit?.value, 'voice', pq)
    return
  }

  if (st.awaitingCommand) {
    st.awaitingCommand = false
    clearCommandTimer()
    statusLine.value = ''
    if (state.value === 'recording') state.value = 'listening'
    st.turnToken++             // 认领发送权
    enterWakeCooldown()
    st.deps.sendText(trimmed)
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
        st.turnToken++
        enterWakeCooldown()
        clearFollowupTimer()
        st.deps.sendText(rf.command)
      } else {
        st.awaitingCommand = true
        statusLine.value = '已唤醒，请说指令…'
        state.value = 'recording'
        armCommandTimer()
      }
      return
    }
    st.turnToken++
    clearFollowupTimer()
    st.deps.sendText(trimmed)
    return
  }

  // 终审 Important #1（守卫半）：通话态 KWS 闸门暂停（spec）——不判唤醒词。
  // webspeech 分支在通话期不被 acquireAndStart 选择，此处钉住即便有迟到的 final result
  // 也不会触发 detectWake；作答/指令/续聊通道在其上不受影响。
  // Final-review Important #1 (guard half): the KWS gate pauses during a call (spec) — no
  // wake judging. acquireAndStart no longer selects the webspeech branch mid-call; this
  // pins that even a late final result cannot reach detectWake. The answer/command/
  // followup channels above are unaffected.
  if (callActive.value) return

  const r = detectWake(trimmed, wakeKeywords.value)
  if (!r.matched) return
  if (r.command) { st.turnToken++; enterWakeCooldown(); st.deps.sendText(r.command); return }

  st.awaitingCommand = true
  statusLine.value = '已唤醒，请说指令…'
  if (state.value === 'listening') state.value = 'recording'
  playBeep()
  armCommandTimer()
}
