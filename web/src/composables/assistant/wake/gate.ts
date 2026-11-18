// 拆分自 orchState.ts：上传闸门、回声护栏、提示音与 barge-in 终止。
// Split from orchState.ts: upload gate, echo guard, cue and barge-in termination.

import { state, vadConfig, pendingQuestion, callActive } from '../store'
import type { StreamGate } from '../stream/streamClient'
import { st } from './orchStore'

/**
 * 当前应使用的上传闸门。
 *
 * upload gate for the current context:
 * - 通话 / 待答 / 指令窗 / 续聊：open（免唤醒，不能被 KWS 拦截）
 * - 其余（聆听/静待）：wake（KWS 未命中不上云）
 *
 * @returns 闸门模式。The gate mode.
 */
export function currentGate(): StreamGate {
  if (callActive.value || pendingQuestion.value || st.awaitingCommand) return 'open'
  if (st.followupActive || state.value === 'awaiting_answer' || state.value === 'recording') {
    return 'open'
  }
  return 'wake'
}

/** 把当前闸门同步给流式连接（无连接/旧句柄时静默）。
 *  Push the current gate to the stream (silent when absent or on a legacy handle). */
export function syncStreamGate(): void {
  st.voiceStream?.setGate?.(currentGate())
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
