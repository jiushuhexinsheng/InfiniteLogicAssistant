/**
 * 语音电源开关 + 通话聆听入口（2026-10-11 用户状态图重定义，取代 2026-10-05 的
 * 「双击进通话漏斗」spec）：
 *
 *   关闭态(idle) ──双击──▶ 静待(standby：麦开、本地 KWS 侦听，= 唤醒前)
 *   静待 ──喊唤醒词──▶ 通话聆听中(callActive+listening：漏斗持续聆听)
 *   通话聆听中 ──静止 listen_idle_s──▶ 静待（orchState 空闲超时自动干净退出漏斗）
 *   任意开启态 ──双击──▶ 关闭态（麦关；通话中先 callStop）
 *
 * 单一链条、没有两个模式：双击是**电源**，唤醒词是**唤醒点**，静待=唤醒前。
 *
 * Voice power toggle + call-listening entry (2026-10-11 user state-diagram redefinition,
 * superseding the 2026-10-05 "double-click enters the funnel" spec): double-click is the
 * POWER (off ⇄ standby), the wake word is the WAKE POINT (standby → call listening), and
 * the idle timeout walks call listening back to standby. One chain, no two modes;
 * standby IS the pre-wake state.
 */
import { api } from '../../api'
import { callActive, callConfig, state, statusLine, wakeEnabled } from './store'
import { startListening, stopListening, ensureListening } from './wake/wakeOrchestrator'
import type { AsstState } from './store'

/** 开启态集合：处于其中任一状态 = 语音开着（双击应执行「关闭」）。
 *  Set of powered-on states: being in any of them means the mic is live (a double-click
 *  should power OFF). */
const POWERED_STATES: AsstState[] = [
  'listening', 'standby', 'recording', 'transcribing', 'awaiting_answer', 'followup', 'thinking', 'tool_calling', 'responding',
]

function isPowered(): boolean {
  return wakeEnabled.value || callActive.value || POWERED_STATES.includes(state.value)
}

/** 关闭语音：停通话会话（若有）、停麦、回关闭态。Power off: end the call session (if
 *  any), stop the mic, return to the off state. */
async function powerOff(): Promise<void> {
  const wasCall = callActive.value
  callActive.value = false
  stopListening()
  wakeEnabled.value = false
  state.value = 'idle'
  statusLine.value = ''
  if (wasCall) {
    try { await api.callStop() } catch { /* 会话服务端 5 分钟自过期兜底 */ }
  }
}

/**
 * 双击 = 语音电源开关。开启直接落**静待**（唤醒前状态：麦开 + 本地 KWS 侦听），
 * 不再进入通话漏斗 —— 漏斗由唤醒词从静待唤醒后进入（enterCallFromWake）。
 *
 * Double-click is the voice power switch. Power-on lands directly in **standby** (the
 * pre-wake state: mic live + local KWS listening) instead of entering the call funnel —
 * the funnel is entered by waking from standby with the wake word (enterCallFromWake).
 */
export async function togglePower(): Promise<void> {
  if (isPowered()) {
    await powerOff()
    return
  }
  const r = await startListening()   // 取流 + wakeEnabled=true + state=listening
  if (r !== 'ok') {
    statusLine.value = typeof r === 'string' ? r : '麦克风启动失败'
    return
  }
  state.value = 'standby'            // 开机即唤醒前（静待），等唤醒词
  statusLine.value = ''
}

/** 旧名保留：callMode 的双击入口现在是电源开关（togglePower）。
 *  Kept alias: callMode's double-click entry is now the power switch (togglePower). */
export const toggleCall = togglePower

/**
 * 静待中喊唤醒词 → 进入**通话聆听中**（打开后端通话会话、漏斗接管段落判定）。
 * 麦已在听（段录音器运行中），只切路由不碰麦克风。返回是否进入成功 ——
 * 失败/未启用时调用方回退既有指令窗语义（不丢唤醒）。
 *
 * Wake word in standby → enter **call listening** (opens the backend call session; the
 * funnel takes over segment judging). The mic is already live, so only the routing flips.
 * Returns whether entry succeeded — on failure/disabled the caller falls back to the
 * existing command-window semantics (the wake is never lost).
 */
export async function enterCallFromWake(): Promise<boolean> {
  if (callActive.value) return true
  if (!callConfig.enabled) return false
  try {
    const r = await api.callStart().catch(() => ({ ok: false }))
    if (!r.ok) {
      statusLine.value = '通话聆听启动失败（后端未就绪），已回退指令窗'
      return false
    }
  } catch {
    return false   // api 桩缺 callStart 等异常 → 回退指令窗（测试与降级路径）
  }
  callActive.value = true
  wakeEnabled.value = true   // 静待的唤醒生命周期（播报回落 ensureListening gate 它）
  state.value = 'listening'  // callActive=true → 视觉/文案 =「通话聆听中」
  statusLine.value = ''
  void ensureListening()     // 兜底：通话期间麦必须在（幂等，已在听则无副作用）
  return true
}
