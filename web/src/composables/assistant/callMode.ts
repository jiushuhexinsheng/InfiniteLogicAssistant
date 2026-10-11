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
import { startListening, stopListening, toggleWake, wakeEnabled, ensureListening } from './wake/wakeOrchestrator'

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

/** 双击入口：通话 ⇄ 非通话。退出落点按进通话前的唤醒快照 —— 之前开着唤醒的人回
 *  **listening 并重新拉起麦克风**（喊唤醒词立刻可用）；之前关着的回 idle（麦保持关）。
 *  旧实现无条件落 idle + wakeEnabled 恢复 true：麦已停、state 又不在任何会触发
 *  ensureListening 的路径上 → 退出通话后唤醒词永久喊不应（2026-10-11 现场复盘）。
 *  Double-click entry: call ⇄ non-call. The exit landing follows the pre-call wake
 *  snapshot — someone who had wake on returns to **listening with the mic re-acquired**
 *  (the wake word works immediately); wake-off returns to idle (mic stays off). The old
 *  build unconditionally landed on idle with wakeEnabled restored true: the mic was off
 *  and no path would call ensureListening, so the wake word stayed dead forever after
 *  leaving a call (2026-10-11 field post-mortem). */
export async function toggleCall(): Promise<void> {
  if (!callConfig.enabled) {
    statusLine.value = '通话模式未启用（voice.call.enabled=false）'
    return
  }
  if (callActive.value) {
    callActive.value = false
    stopListening()
    wakeEnabled.value = wakeWasOnBeforeCall   // 回收 startListening 的置位（终审 Important #2）
    statusLine.value = ''
    if (wakeWasOnBeforeCall) {
      state.value = 'listening'     // 唤醒点恢复：静待/空闲都不是退出通话的落点。
      void ensureListening()        // 重新取流（stopListening 已释放旧麦）。
    } else {
      state.value = 'idle'
    }
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
