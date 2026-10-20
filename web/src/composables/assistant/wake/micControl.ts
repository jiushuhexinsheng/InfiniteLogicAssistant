import {
  state, statusLine, wakeEnabled, failWake, hardwareConfig, streamingEnabled,
} from '../store'
import { st, clearWaitTimers, resetFailures, stopBargeIn } from './orchState'
import { createVoiceStream, type VoiceStreamHandle } from '../stream/streamClient'
import { handleStreamEvent } from '../stream/streamFlow'
import { clearTranscript, setStreamPhase, streamError } from '../storeTranscript'
import { reportMicLevel, resetMicLevel } from '../micLevel'
// 流式语音麦克风控制：取流 → AudioWorklet → WebSocket；旧切段/Web Speech 链路已删除。
// Streaming mic control: stream → AudioWorklet → WebSocket; the legacy segment / Web
// Speech pipeline is gone.

// ── 停止监听 ──

export function stopListening() {
  st.listenGen++
  st.awaitingCommand = false
  clearWaitTimers()
  if (state.value === 'recording') state.value = wakeEnabled.value ? 'listening' : 'idle'

  if (st.voiceStream) {
    try { st.voiceStream.stop() } catch (e) { console.error('[wake] voiceStream stop error:', e) }
    st.voiceStream = null
  }
  clearTranscript()
  if (!streamError.value) setStreamPhase('idle')
  resetMicLevel()   // 兜底归零（声波条回落）。Belt-and-braces zero for the level bars.
}

// ── 取流 ──

type AcquireOutcome = 'ok' | 'mic-error' | 'aborted'

async function acquireAndStart(): Promise<AcquireOutcome> {
  if (st.voiceStream) return 'ok'
  if (!streamingEnabled.value) {
    statusLine.value = '流式语音已关闭（voice.streaming.enabled=false）'
    return 'mic-error'
  }
  if (typeof window === 'undefined'
      || !(window.AudioContext || (window as any).webkitAudioContext)
      || typeof WebSocket === 'undefined') {
    statusLine.value = '当前浏览器不支持流式语音（需要 AudioContext + WebSocket）'
    return 'mic-error'
  }

  const gen = st.listenGen
  setStreamPhase('loading')
  let handle: VoiceStreamHandle
  handle = createVoiceStream({
    onEvent: (ev) => {
      void handleStreamEvent(ev).catch((e) => console.warn('[wake] stream event error:', e))
    },
    onLevel: reportMicLevel,
    onError: (e) => {
      statusLine.value = e.message
      setStreamPhase('error', e.message)
    },
    onClose: () => {
      if (st.voiceStream === handle) st.voiceStream = null
      if (!streamError.value) setStreamPhase('idle')
    },
    inputDevice: hardwareConfig.input_device,
    echoCancellation: hardwareConfig.echo_cancellation,
    noiseSuppression: hardwareConfig.noise_suppression,
    autoGain: hardwareConfig.auto_gain,
  })
  try {
    await handle.start()
  } catch (e) {
    console.warn('[wake] voice stream start failed:', e)
    handle.stop()
    // 服务端错误（模型缺失/加载失败）原样展示；麦克风错误走可操作文案。
    // Server errors (missing/failed model) are shown verbatim; mic errors get actionable copy.
    const err = e as { server?: boolean; message?: string }
    const message = err?.server
      ? (err.message || '语音服务启动失败')
      : describeMicError(e)
    statusLine.value = message
    setStreamPhase('error', message)
    return 'mic-error'
  }
  if (gen !== st.listenGen) {
    handle.stop()
    return 'aborted'
  }
  st.voiceStream = handle
  setStreamPhase('ready')
  return 'ok'
}

export async function ensureListening(): Promise<boolean> {
  if (!wakeEnabled.value) return false
  return (await acquireAndStart()) === 'ok'
}

// ── 麦克风错误描述 ──

export function describeMicError(e: any): string {
  const name = e?.name || ''
  switch (name) {
    case 'NotFoundError':
    case 'DevicesNotFoundError':
    case 'OverconstrainedError':
      return '未检测到可用麦克风，请检查麦克风连接或系统录音设备设置'
    case 'NotAllowedError':
    case 'PermissionDeniedError':
    case 'SecurityError':
      return '麦克风权限被拒绝，请点击地址栏🔒图标允许麦克风后重试'
    case 'NotReadableError':
    case 'TrackStartError':
    case 'AbortError':
      return '麦克风被其他程序占用或不可读，请关闭占用程序后重试'
    default: {
      const msg = typeof e?.message === 'string' ? e.message.trim() : ''
      return '麦克风访问失败：' + (msg || name || '未知错误')
    }
  }
}

// ── 开启/关闭唤醒 ──

/** 启动被打断（取流途中被停）的提示文案。Message shown when startup is aborted. */
const START_ABORTED_MSG = '唤醒启动被打断，请再点一次'

/** 启动监听序列（toggleWake 的 enable 分支体）。返回 'ok' | 'aborted' | 错误文案。 */
export async function startListening(): Promise<'ok' | 'aborted' | string> {
  statusLine.value = '正在启动唤醒...'
  try {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const mics = devices.filter((d) => d.kind === 'audioinput')
      if (mics.length === 0) {
        console.warn('[wake] no audioinput device found')
        return '系统未检测到麦克风设备，请连接/启用麦克风后重试'
      }
    } catch (e) {
      console.warn('[wake] enumerateDevices fail:', e)
    }
    const outcome = await acquireAndStart()
    if (outcome !== 'ok') return outcome === 'aborted' ? START_ABORTED_MSG : (statusLine.value || '麦克风启动失败，请检查系统/浏览器麦克风权限')
    wakeEnabled.value = true
    state.value = 'listening'
    statusLine.value = ''
    return 'ok'
  } finally {
    st.startingWake = false
  }
}

export async function toggleWake() {
  console.log('[wake] toggleWake called, current state:', state.value)
  statusLine.value = ''
  resetFailures()

  // followup 与 done/error 同属「回合刚结束」窗口：录音器可能还活着 → acquireAndStart
  // 复用（与 done 窗口单击的既有语义一致），不重建。
  if (state.value === 'idle' || state.value === 'done' || state.value === 'error'
      || state.value === 'followup') {
    if (st.startingWake) {
      console.log('[wake] enable already in flight, ignoring')
      return
    }
    st.startingWake = true   // 置位留在 toggleWake；startListening 的 finally 只负责清位。
    const r = await startListening()
    if (r === 'ok') {
      // 与双击电源同一落点：开机 = 唤醒前 = 静待。
      state.value = 'standby'
      console.log('[wake] listening started!')
    } else if (r === START_ABORTED_MSG) {
      statusLine.value = r   // 打断是良性竞态：原样提示，不进错误态。
    } else {
      failWake(r)
    }
  } else {
    console.log('[wake] stopping...')
    stopListening()
    wakeEnabled.value = false
    state.value = 'idle'
    clearTranscript()
    statusLine.value = ''
  }
}

// ── 停止（页面销毁时调用）──

export function stopWake() {
  st.turnToken++          // 停止监听 → 作废在飞的尾随提取（停止后不得再发指令）
  stopBargeIn()
  stopListening()
}
