import { state, statusLine, partialText, wakeEnabled, vadConfig, wakeMode, callActive, failWake } from '../store'
import { createSegmentRecorder } from '../useSegmentRecorder'
import { getWebSpeechProvider, peekWebSpeechProvider, disposeAll } from './wakeChain'
import { handleSegment } from './segmentFlow'
import { handleLocalResult } from './localResult'
import { st, clearWaitTimers, resetFailures, stopBargeIn } from './orchState'
// 拆分自 wakeOrchestrator.ts（重构：纯移动 + 状态收敛到 orchState.st，无行为变化）。
// Split from wakeOrchestrator.ts (pure move; mutable state consolidated into orchState.st).
// ── 分段录音器 ──

function startSegmenter() {
  if (!st.micStream) return
  st.segmenter = createSegmentRecorder(st.micStream, {
    speechThreshold: vadConfig.silence_threshold,
    silenceMs: vadConfig.silence_duration_ms,
    minSpeechMs: vadConfig.min_speech_ms,
    maxMs: vadConfig.max_duration_ms,
    onSegment: (b) => {
      void handleSegment(b).catch((e) => console.warn('[wake] handleSegment error:', e))
    },
  })
  st.segmenter.start()
}

// ── 停止监听 ──

export function stopListening() {
  st.listenGen++
  st.awaitingCommand = false
  clearWaitTimers()
  if (state.value === 'recording') state.value = wakeEnabled.value ? 'listening' : 'idle'

  const wsp = peekWebSpeechProvider()
  if (wsp?.isRunning()) wsp.stop()

  if (st.segmenter) {
    try { st.segmenter.stop() } catch (e) { console.error('[wake] st.segmenter stop error:', e) }
    st.segmenter = null
  }
  if (st.micStream) {
    try { st.micStream.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    st.micStream = null
  }
}

// ── 取流 ──

type AcquireOutcome = 'ok' | 'mic-error' | 'aborted'

async function acquireAndStart(): Promise<AcquireOutcome> {
  const mode = wakeMode.value

  // 终审 Important #1：webspeech 分支只在非通话态选路。通话期强制 st.segmenter —— 否则
  // WebSpeech 的 final result 只进 handleLocalResult，永不产生 call/segment，免唤醒说话
  // 被静默丢弃（且 detectWake 照常执行，违反「通话激活时 KWS 闸门暂停」）。st.segmenter 路
  // 不依赖 KWS 模型（漏斗判在后端），webspeech 用户可用；退出通话自然回落 webspeech。
  // Final-review Important #1: the webspeech branch is selected only outside a call. During
  // a call the st.segmenter path is forced — otherwise a WebSpeech final result only reaches
  // handleLocalResult, never produces call/segment, and wake-free speech is silently lost
  // (detectWake also keeps running, violating "the KWS gate pauses while a call is active").
  // The st.segmenter path needs no KWS model (the funnel judges server-side), so it works for
  // webspeech users; exiting the call falls back to webspeech naturally.
  if (mode === 'webspeech' && !callActive.value) {
    const wsp = getWebSpeechProvider()
    if (wsp.isRunning()) return 'ok'
    if (!wsp.isAvailable()) {
      statusLine.value = '⚠️ 当前浏览器不支持 Web Speech API，请切换到其他模式'
      return 'mic-error'
    }
    const started = wsp.start((text, isFinal) => {
      // 中间结果显示到 partialText（悬浮球可以看到正在听的内容）；最终结果清空并处理
      // Interim results shown in partialText (the ball shows what is being heard); final results clear and process
      partialText.value = isFinal ? '' : text
      if (isFinal) handleLocalResult(text)
    })
    if (!started) {
      statusLine.value = '⚠️ Web Speech API 启动失败'
      return 'mic-error'
    }
    return 'ok'
  }

  if (st.segmenter) return 'ok'
  const gen = st.listenGen
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
  } catch (e) {
    console.warn('[wake] getUserMedia failed:', e)
    statusLine.value = describeMicError(e)
    return 'mic-error'
  }
  if (gen !== st.listenGen) {
    try { stream.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    return 'aborted'
  }
  if (st.segmenter) {
    try { stream.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    return 'ok'
  }
  st.micStream = stream
  try {
    startSegmenter()
  } catch (e) {
    console.error('[wake] st.segmenter start failed:', e)
    statusLine.value = '唤醒启动失败，请重试'
    stopListening()
    return 'mic-error'
  }
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

/** 启动被打断（取流途中被停）的提示文案：startListening 的 aborted 分支与 toggleWake
 *  共用一份 —— toggleWake 靠它把良性竞态（原样提示、不进错误态）与真实失败（failWake）
 *  按提取前的行为分开。
 *  Message shown when startup is aborted (the stream was stopped mid-acquisition):
 *  startListening's aborted branch and toggleWake share this one string — toggleWake uses
 *  it to tell a benign race (status line only, no error state) from a real failure
 *  (failWake), exactly as before the extraction. */
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
  // followup is another "turn just ended" window alongside done/error: the recorder may
  // still be live → acquireAndStart reuses it (same semantics as a click in the done
  // window); no rebuild.
  if (state.value === 'idle' || state.value === 'done' || state.value === 'error'
      || state.value === 'followup') {
    if (st.startingWake) {
      console.log('[wake] enable already in flight, ignoring')
      return
    }
    st.startingWake = true   // 置位留在 toggleWake；startListening 的 finally 只负责清位。
    const r = await startListening()
    if (r === 'ok') {
      console.log('[wake] listening started!')
    } else if (r === START_ABORTED_MSG) {
      statusLine.value = r   // 打断是良性竞态：原样提示，不进错误态（行为同提取前）。
    } else {
      failWake(r)
    }
  } else {
    console.log('[wake] stopping...')
    stopListening()
    wakeEnabled.value = false
    state.value = 'idle'
    partialText.value = ''
    statusLine.value = ''
  }
}

// ── 停止（页面销毁时调用）──

export function stopWake() {
  st.turnToken++          // 停止监听 → 作废在飞的尾随提取（停止后不得再发指令）
  stopBargeIn()
  stopListening()
  disposeAll()
}
