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

/** 双击入口：通话 ⇄ 待机。Double-click entry: call ⇄ idle. */
export async function toggleCall(): Promise<void> {
  if (!callConfig.enabled) {
    statusLine.value = '通话模式未启用（voice.call.enabled=false）'
    return
  }
  if (callActive.value) {
    callActive.value = false
    stopListening()
    state.value = 'idle'
    statusLine.value = ''
    try { await api.callStop() } catch { /* 会话服务端 5 分钟自过期兜底 */ }
    return
  }
  // 互斥：唤醒在听先停（Review Focus #3）。
  if (wakeEnabled.value) await toggleWake()
  const r = await api.callStart().catch(() => ({ ok: false }))
  if (!r.ok) {
    statusLine.value = '通话模式启动失败（后端未就绪）'
    return
  }
  callActive.value = true
  const outcome = await startListening()
  if (outcome !== 'ok') {
    callActive.value = false
    await api.callStop().catch(() => {})
    statusLine.value = typeof outcome === 'string' ? outcome : '麦克风启动失败'
    return
  }
}
