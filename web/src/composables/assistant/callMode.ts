/**
 * 通话模式 FSM — 双击悬浮球进入的免唤醒持续聆听（spec: 2026-10-05-call-mode-funnel）。
 *
 * 与唤醒链互斥：进入前先停唤醒、退出后监听全停；开放窗口（回答后的免焦点追问期）
 * 在 store 计时（markTurnEnded/inOpenWindow），段落路由（wakeOrchestrator.processSegment）
 * 读 store.callActive 分流。
 *
 * Call-mode FSM — wake-free continuous listening entered by double-clicking the float
 * ball. Mutually exclusive with the wake chain (wake stops before entry, all listening
 * stops on exit); the open window is timed in the store (markTurnEnded/inOpenWindow)
 * and segment routing reads store.callActive.
 */
import { api } from '../../api'
import { callActive, callConfig, state, statusLine } from './store'
import { startListening, stopListening, toggleWake, wakeEnabled } from './wake/wakeOrchestrator'

/** 进入通话前的 wakeEnabled 快照。
 *  startListening 成功会把 wakeEnabled 置 true（wakeOrchestrator.ts:784），退出分支与失败
 *  回滚必须恢复之 —— 否则唤醒从未被用户打开却被武装：下一次 TTS 播报结束
 *  （wakeOrchestrator.ts:910）`if (wakeEnabled.value) void ensureListening()` 会复活录音器。
 *  模块级而非局部 const：进入与退出是两次独立的 toggleCall 调用，快照必须跨调用存活。
 *  Snapshot of wakeEnabled taken on call entry. startListening sets it true on success
 *  (wakeOrchestrator.ts:784); exit and the failure rollback must restore it, or wake gets
 *  armed though the user never turned it on — the next TTS end (wakeOrchestrator.ts:910)
 *  `if (wakeEnabled.value) void ensureListening()` revives the recorder. Module-level rather
 *  than a local const: entry and exit are separate toggleCall invocations, so the snapshot
 *  must outlive one call. */
let wakeWasOnBeforeCall = false

/** 双击入口：通话 ⇄ 空闲（退出通话回 idle；与已删除的 standby 状态无关）。
 *  Double-click entry: call ⇄ idle (leaving a call returns to idle; unrelated to the
 *  removed standby state). */
export async function toggleCall(): Promise<void> {
  if (!callConfig.enabled) {
    statusLine.value = '通话模式未启用（voice.call.enabled=false）'
    return
  }
  if (callActive.value) {
    callActive.value = false
    stopListening()
    wakeEnabled.value = wakeWasOnBeforeCall   // 回收 startListening 的置位（终审 Important #2）
    state.value = 'idle'
    statusLine.value = ''
    try { await api.callStop() } catch { /* 会话服务端 5 分钟自过期兜底 */ }
    return
  }
  // 进入前先快照（必须在互斥停唤醒之前 —— 停唤醒会把 wakeEnabled 置 false）。
  // Snapshot before entry (it must precede the mutual-exclusion stop: stopping wake sets the flag false).
  wakeWasOnBeforeCall = wakeEnabled.value
  // 互斥：唤醒在听先停（Review Focus #3）。
  if (wakeEnabled.value) await toggleWake()
  const r = await api.callStart().catch(() => ({ ok: false }))
  if (!r.ok) {
    wakeEnabled.value = wakeWasOnBeforeCall   // 互斥停唤醒已发生 → 失败同样恢复快照
    statusLine.value = '通话模式启动失败（后端未就绪）'
    return
  }
  callActive.value = true
  const outcome = await startListening()
  if (outcome !== 'ok') {
    callActive.value = false
    wakeEnabled.value = wakeWasOnBeforeCall   // 失败回滚同恢复快照（终审 Important #2）
    await api.callStop().catch(() => {})
    statusLine.value = typeof outcome === 'string' ? outcome : '麦克风启动失败'
    return
  }
}
