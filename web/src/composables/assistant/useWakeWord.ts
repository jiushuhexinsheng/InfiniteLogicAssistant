import { api } from '../../api'
import { state, partialText, statusLine, expanded, wakeEnabled, wakeConfig, vadConfig, addMessage, failWake, modelLoading, modelProgress } from './store'
import { runTurn } from './useChat'

// ── 录音管线 ──
let wakeRecorder: MediaRecorder | null = null
let wakeChunks: Blob[] = []
let silenceTimer: ReturnType<typeof setInterval> | null = null
let maxTimer: ReturnType<typeof setTimeout> | null = null
let vadAudioCtx: AudioContext | null = null

// ── 唤醒词引擎 ──
let modelLoaded = false

/** 带进度下载模型字节（约 44MB tar.gz），供 vosk.createModel 初始化。 */
async function fetchModel(url: string, onProgress: (pct: number) => void): Promise<ArrayBuffer> {
  const resp = await fetch(url)
  if (!resp.ok || !resp.body) throw new Error(`模型下载失败: HTTP ${resp.status}`)
  const total = Number(resp.headers.get('Content-Length')) || 0
  const reader = resp.body.getReader()
  const chunks: Uint8Array[] = []
  let received = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) { chunks.push(value); received += value.length }
    if (total) onProgress(Math.min(100, Math.round((received / total) * 100)))
  }
  const all = new Uint8Array(received)
  let off = 0
  for (const c of chunks) { all.set(c, off); off += c.length }
  return all.buffer
}

async function initWakeModel() {
  if (typeof WakeWordEngine === 'undefined') {
    console.warn('[Asst] WakeWordEngine missing')
    return false
  }
  if (modelLoaded) return true
  try {
    modelLoading.value = true
    modelProgress.value = 0
    statusLine.value = '正在下载唤醒模型 0%...'
    const buf = await fetchModel(wakeConfig.model_path, (pct) => {
      modelProgress.value = pct
      statusLine.value = pct >= 100 ? '正在初始化语音模型...' : `正在下载唤醒模型 ${pct}%...`
    })
    const ok = await WakeWordEngine.init({
      modelPath: wakeConfig.model_path,
      keyword: wakeConfig.keyword,
      sensitivity: wakeConfig.sensitivity,
      model: buf,
    })
    modelLoaded = ok
    modelLoading.value = false
    modelProgress.value = 100
    statusLine.value = ok ? '' : '模型加载失败'
    return ok
  } catch (e) {
    console.error('[Asst] model init fail:', e)
    modelLoading.value = false
    statusLine.value = '模型加载失败'
    return false
  }
}

function playBeep() {
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

function clearTimers() {
  if (silenceTimer) { clearInterval(silenceTimer); silenceTimer = null }
  if (maxTimer) { clearTimeout(maxTimer); maxTimer = null }
  if (vadAudioCtx) { try { vadAudioCtx.close() } catch { /* ignore */ } vadAudioCtx = null }
}

// ── 麦克风错误 → 用户可理解的中文提示（getUserMedia 常见异常映射）──
function describeMicError(e: any): string {
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
    default:
      return '麦克风访问失败: ' + (e?.message || name || '未知错误')
  }
}

function stopRecording() {
  clearTimers()
  if (wakeRecorder && wakeRecorder.state === 'recording') {
    wakeRecorder.stop()
  }
}

function startVAD(stream: MediaStream) {
  let analyser: AnalyserNode | null = null
  try {
    // 关闭上一次残留的 AudioContext
    if (vadAudioCtx) { try { vadAudioCtx.close() } catch { /* ignore */ } }
    vadAudioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
    const ctx = vadAudioCtx
    const source = ctx.createMediaStreamSource(stream)
    analyser = ctx.createAnalyser()
    analyser.fftSize = 2048
    analyser.smoothingTimeConstant = 0.3
    source.connect(analyser)
  } catch (e) { return }

  const threshold = vadConfig.silence_threshold || 0.02
  const silenceMs = vadConfig.silence_duration_ms || 1500
  const checkInterval = 100
  const maxSilence = Math.ceil(silenceMs / checkInterval)
  let silenceCount = 0
  let elapsed = 0
  const minSpeakTime = 2000

  silenceTimer = setInterval(() => {
    if (!analyser || !wakeRecorder || wakeRecorder.state !== 'recording') {
      clearTimers()
      return
    }
    elapsed += checkInterval
    const dataArray = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(dataArray)
    let sum = 0
    for (let i = 0; i < dataArray.length; i++) {
      const v = (dataArray[i] - 128) / 128
      sum += v * v
    }
    const rms = Math.sqrt(sum / dataArray.length)

    if (elapsed < minSpeakTime) return
    if (rms < threshold) {
      silenceCount++
      if (silenceCount >= maxSilence) {
        stopRecording()
      }
    } else {
      silenceCount = 0
    }
  }, checkInterval)
}

function startMaxTimer() {
  maxTimer = setTimeout(() => {
    console.log('[Asst] max duration reached')
    stopRecording()
  }, vadConfig.max_duration_ms || 10000)
}

// ── 唤醒检测回调 ──
function onWakeDetected() {
  console.log('[Asst] WAKE!')
  state.value = 'recording'
  playBeep()

  const stream = WakeWordEngine.getStream()
  if (!stream) { state.value = 'listening'; return }

  wakeChunks = []
  let mimeType = 'audio/webm'
  if (!MediaRecorder.isTypeSupported(mimeType)) {
    mimeType = 'audio/webm;codecs=opus'
    if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = ''
  }
  const opts: MediaRecorderOptions = {}
  if (mimeType) opts.mimeType = mimeType

  try {
    wakeRecorder = new MediaRecorder(stream, opts)
  } catch (e) {
    console.error('[Asst] MediaRecorder fail:', e)
    state.value = 'listening'
    return
  }

  wakeRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) wakeChunks.push(e.data)
  }

  wakeRecorder.onstop = async () => {
    clearTimers()
    if (wakeChunks.length === 0) { state.value = 'listening'; return }

    state.value = 'transcribing'
    const blob = new Blob(wakeChunks, { type: mimeType || 'audio/webm' })
    wakeChunks = []
    console.log('[Asst] recording done, size:', blob.size)

    await handleTranscript(blob)

    // 回到聆听状态
    setTimeout(() => {
      if (state.value === 'done' || state.value === 'error') {
        state.value = 'listening'
      }
    }, 3000)
  }

  wakeRecorder.start(1000)
  startVAD(stream)
  startMaxTimer()
}

// ── ASR 转写 ──
async function handleTranscript(blob: Blob) {
  try {
    const r = await api.transcribe(blob)
    if (r.ok && r.text) {
      const text = r.text.trim()
      if (!text) { state.value = 'listening'; return }
      partialText.value = text
      addMessage('user', text)
      await runTurn()
    } else {
      addMessage('system', '转写失败: ' + (r.error || '无结果'))
      state.value = 'listening'
    }
  } catch (e: any) {
    console.error('[Asst] transcribe error:', e)
    addMessage('system', '转写异常: ' + (e.message || ''))
    state.value = 'error'
  }
}

// ── 开启/关闭唤醒 ──
export async function toggleWake() {
  console.log('[Asst] toggleWake called, current state:', state.value, 'modelLoaded:', modelLoaded)
  statusLine.value = ''

  if (state.value === 'idle' || state.value === 'done' || state.value === 'error') {
    // ── 开启 ──
    if (typeof WakeWordEngine === 'undefined') {
      console.error('[Asst] WakeWordEngine not defined')
      failWake('唤醒引擎未加载，请刷新页面重试')
      return
    }

    if (!modelLoaded) {
      statusLine.value = '正在加载语音模型...'
      state.value = 'listening' // 先切到 listening 让用户看到变化
      console.log('[Asst] loading model...')
      try {
        const ok = await initWakeModel()
        if (!ok) {
          console.error('[Asst] model init failed')
          failWake('语音模型加载失败，请刷新页面重试')
          return
        }
      } catch (e: any) {
        console.error('[Asst] model init exception:', e)
        failWake('语音模型加载异常: ' + (e.message || e))
        return
      }
    }

    statusLine.value = '正在启动唤醒...'
    console.log('[Asst] starting WakeWordEngine...')

    // 预检麦克风设备：无可用录音设备时提前提示，避免模糊的 NotFoundError
    try {
      const devices = await navigator.mediaDevices.enumerateDevices()
      const mics = devices.filter((d) => d.kind === 'audioinput')
      if (mics.length === 0) {
        console.warn('[Asst] no audioinput device found')
        failWake('系统未检测到麦克风设备，请连接/启用麦克风后重试')
        return
      }
      console.log('[Asst] audioinput devices:', mics.map((m) => m.label || '(未授权标签)').join(', '))
    } catch (e) {
      console.warn('[Asst] enumerateDevices fail:', e)
    }

    try {
      // start() 内部会 catch 错误并返回 false（如麦克风被系统/浏览器拦截），需检查返回值
      const started = await WakeWordEngine.start(onWakeDetected, (info: any) => {
        partialText.value = info.partial || ''
      })
      if (!started) {
        console.warn('[Asst] WakeWordEngine.start returned false')
        failWake('麦克风启动失败，请检查系统/浏览器麦克风权限')
        return
      }
      wakeEnabled.value = true
      state.value = 'listening'
      statusLine.value = ''
      console.log('[Asst] listening started!')
    } catch (e: any) {
      console.error('[Asst] WakeWordEngine.start failed:', e)
      failWake(describeMicError(e))
    }
  } else {
    // ── 关闭 ──
    console.log('[Asst] stopping...')
    try { WakeWordEngine.stop() } catch (e) { console.error('[Asst] stop error:', e) }
    wakeEnabled.value = false
    state.value = 'idle'
    partialText.value = ''
    statusLine.value = ''
  }
}

// ── 页面销毁时收尾：停唤醒、清定时器、停录音 ──
export function stopWake() {
  try { WakeWordEngine.stop() } catch { /* ignore */ }
  clearTimers()
  if (wakeRecorder && wakeRecorder.state !== 'inactive') {
    try { wakeRecorder.stop() } catch { /* ignore */ }
  }
}
