import { watch } from 'vue'
import { api } from '../../api'
import { formatError } from '../../errors'
import { nextState } from './wakeFsm'
import { speaking } from './useTts'
import { state, partialText, statusLine, expanded, wakeEnabled, wakeConfig, vadConfig, addMessage, failWake, modelLoading, modelProgress, pendingQuestion } from './store'
import { runTurn, sendAnswer } from './useChat'
import { matchOption } from './answerMatch'

/** 录音管线相关变量。Recording pipeline variables. */
let wakeRecorder: MediaRecorder | null = null
let wakeChunks: Blob[] = []
let silenceTimer: ReturnType<typeof setInterval> | null = null
let maxTimer: ReturnType<typeof setTimeout> | null = null
let vadAudioCtx: AudioContext | null = null

/** 唤醒词引擎加载状态。Wake word engine loading state. */
let modelLoaded = false

/** 初始化唤醒模型。Initialize wake word model.
 *  注意：vosk.js 的 worker 只支持按 URL 加载模型（load() 内 modelUrl.replace），
 *  不支持传入 ArrayBuffer 字节——因此不能预下载字节，直接交给引擎按 URL 下载/解压
 *  （首次约 44MB，之后走 IndexedDB 缓存）。
 *  Note: vosk.js worker only supports URL-based model loading (modelUrl.replace in load()),
 *  does not support ArrayBuffer input — so cannot pre-download bytes, let engine download/decompress by URL
 *  (first time ~44MB, then IndexedDB cached).
 *  @returns 模型是否加载成功。Whether model loaded successfully. */
async function initWakeModel() {
  if (typeof WakeWordEngine === 'undefined') {
    console.warn('[Asst] WakeWordEngine missing')
    return false
  }
  if (modelLoaded) return true
  try {
    modelLoading.value = true
    statusLine.value = '正在加载语音模型（首次需下载约 44MB，请稍候）...'
    const ok = await WakeWordEngine.init({
      modelPath: wakeConfig.model_path,
      keyword: wakeConfig.keyword,
      sensitivity: wakeConfig.sensitivity,
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

/** 初始化唤醒模型（供测试与 toggleWake 复用）。
 *  Initialize wake word model (shared by tests and toggleWake). */
export { initWakeModel }

/** 播放提示音。Play beep sound. */
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

/** 清除所有定时器。Clear all timers. */
function clearTimers() {
  if (silenceTimer) { clearInterval(silenceTimer); silenceTimer = null }
  if (maxTimer) { clearTimeout(maxTimer); maxTimer = null }
  if (vadAudioCtx) { try { vadAudioCtx.close() } catch { /* ignore */ } vadAudioCtx = null }
}

/** 麦克风错误 → 用户可理解的中文提示（getUserMedia 常见异常映射）。
 *  Microphone error → user-friendly Chinese message (common getUserMedia exception mapping).
 *
 *  说明：此处不走 formatError —— 它只覆盖 message，而本函数需要
 *  「message → 错误名 → 未知错误」三段兜底（getUserMedia 抛出的 DOMException
 *  可能 message 为空但 name 有值，丢 name 会损失诊断信息）。
 *
 *  Note: this does not go through formatError, which only covers the message.
 *  This function needs a three-step fallback (message → error name → generic):
 *  DOMExceptions from getUserMedia may have an empty message but a meaningful
 *  name, and dropping the name would lose diagnostic information.
 *
 *  @param e - 错误对象。Error object.
 *  @returns 用户友好的错误消息。User-friendly error message. */
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

/** 本次录音是否因「待答超时」而停止（无音频可转写，不再走转写流程）。
 *  Whether this recording stopped because the answer wait timed out (nothing to transcribe). */
let silentStop = false

/** 停止录音。`silent` 用于待答超时：不再转写，直接返回。
 *  Stop recording. `silent` is used for the answer-wait timeout: nothing to transcribe.
 *  @param opts.silent - 是否为静默停止（待答超时）。Whether this is a silent stop.
 */
function stopRecording(opts?: { silent?: boolean }) {
  silentStop = opts?.silent === true
  clearTimers()
  if (wakeRecorder && wakeRecorder.state === 'recording') {
    wakeRecorder.stop()
  }
}

/** 启动 VAD（语音活动检测）。Start VAD (Voice Activity Detection).
 *  @param stream - 媒体流。Media stream. */
function startVAD(stream: MediaStream) {
  let analyser: AnalyserNode | null = null
  try {
    // 关闭上一次残留的 AudioContext。
    // Close residual AudioContext from previous session.
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
  /** 本次录音是否已检测到语音。待答态下用它区分「用户在说」与「用户在犹豫」。 */
  /** Whether speech has been detected in this recording; lets the answer state tell
   *  "the user is speaking" from "the user is hesitating". */
  let speechStarted = false

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
      if (!speechStarted) {
        speechStarted = true
        const ns = nextState(state.value, 'speech_started')
        if (ns !== state.value) state.value = ns
      }
    }
  }, checkInterval)
}

/** 待答时长（毫秒）：来自 vad.answer_timeout_ms，缺省 8s。
 *  Answer-wait duration in ms, from vad.answer_timeout_ms (default 8s). */
function answerTimeoutMs(): number {
  const ms = (vadConfig as { answer_timeout_ms?: number }).answer_timeout_ms
  return ms && ms > 0 ? ms : 8000
}

/** 启动最大录音时长定时器。`ms` 缺省用 VAD 的 max_duration_ms；待答态传 answer_timeout_s。
 *  Start the max recording timer; `ms` defaults to the VAD's max_duration_ms, while the
 *  answer-wait state passes answer_timeout_s.
 *  @param ms - 超时毫秒数。Timeout in milliseconds. */
function startMaxTimer(ms?: number) {
  maxTimer = setTimeout(() => {
    console.log('[Asst] max duration reached')
    // 待答态超时 = 用户全程未说话 → 进待机（不转写）。
    // 其余态维持既有行为（正常停止并转写已录内容）。
    // An answer-wait timeout means the user never spoke → standby (no transcription).
    const ns = nextState(state.value, 'answer_timeout')
    if (ns !== state.value) {
      state.value = ns
      stopRecording({ silent: true })
      return
    }
    stopRecording()
  }, ms ?? (vadConfig.max_duration_ms || 10000))
}

/** 开始一次录音：取引擎的麦克风流、建 MediaRecorder、接 VAD 与超时。
 *
 * 抽出供「唤醒命中」与「播报后自动开录」共用 —— 避免两份录音逻辑各自演化。
 *
 * Start a recording: take the engine's mic stream, build the MediaRecorder, attach VAD and
 * the timeout. Extracted so "wake detected" and "auto-record after the question is spoken"
 * share one implementation instead of two copies drifting apart.
 *
 * @param timeoutMs 最大录音时长；缺省用 VAD 的 max_duration_ms。Max duration; defaults to the VAD's max_duration_ms.
 * @returns 是否成功开始。Whether recording started.
 */
function startRecording(timeoutMs?: number): boolean {
  const stream = WakeWordEngine.getStream()
  if (!stream) return false

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
    return false
  }

  wakeRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) wakeChunks.push(e.data)
  }

  wakeRecorder.onstop = async () => {
    clearTimers()
    // 待答超时：无音频可转写，状态已由 startMaxTimer 置为待机，直接返回。
    // Answer-wait timeout: nothing to transcribe; standby was already set by startMaxTimer.
    if (silentStop) { silentStop = false; return }
    if (wakeChunks.length === 0) {
      // 待答态没录到内容 → 待机（等用户再唤醒）；其余态回聆听。
      // Nothing recorded while awaiting an answer → standby; otherwise back to listening.
      const ns = nextState(state.value, 'answer_timeout')
      state.value = ns !== state.value ? ns : 'listening'
      return
    }

    state.value = 'transcribing'
    const blob = new Blob(wakeChunks, { type: mimeType || 'audio/webm' })
    wakeChunks = []
    console.log('[Asst] recording done, size:', blob.size)

    await handleTranscript(blob)

    // 回到聆听状态。Return to listening state.
    setTimeout(() => {
      if (state.value === 'done' || state.value === 'error') {
        state.value = 'listening'
      }
    }, 3000)
  }

  wakeRecorder.start(1000)
  startVAD(stream)
  startMaxTimer(timeoutMs)
  return true
}

/** 唤醒检测回调。Wake detection callback. */
function onWakeDetected() {
  console.log('[Asst] WAKE!')
  // 待机态唤醒 → 续答本题（用待答超时而非最大录音时长）；其余态维持既有行为。
  // Waking from standby resumes this question (using the answer timeout rather than the
  // max recording duration); other states keep their existing behaviour.
  const resumed = nextState(state.value, 'wake_detected') === 'awaiting_answer'
  state.value = resumed ? 'awaiting_answer' : 'recording'
  if (!resumed) playBeep()

  if (!startRecording(resumed ? answerTimeoutMs() : undefined)) {
    state.value = 'listening'
  }
}

/** ASR 转写处理：提问待答时走答案通道，否则开新一轮。
 *
 * 提问待答时**绝不能**走 runTurn —— 那会开一条新的 /voice/utter 并 abort 掉当前流，
 * 使后端阻塞中的 ask() 永久挂死（这正是本设计要修的既有缺陷）。
 *
 * ASR transcription handling: a pending question routes to the answer channel, otherwise a
 * new turn starts. While a question is pending it must NEVER call runTurn — that opens a
 * new /voice/utter and aborts the current stream, leaving the backend's blocked ask()
 * hanging forever (the existing defect this design fixes).
 *
 * @param blob 录音音频。The recorded audio.
 */
export async function handleTranscript(blob: Blob) {
  try {
    const r = await api.transcribe(blob)
    if (r.ok && r.text) {
      const text = r.text.trim()
      if (!text) { state.value = 'listening'; return }
      partialText.value = text
      const pq = pendingQuestion.value
      if (pq) {
        // 精确匹配到选项则回传该选项的 value；否则整段作为文本作答。
        // An exact option match returns that option's value; otherwise the whole text is
        // submitted as free text.
        const matched = matchOption(text, pq.options)
        await sendAnswer(matched ? '' : text, matched?.value)
        return
      }
      addMessage('user', text)
      await runTurn()
    } else {
      addMessage('system', '转写失败：' + (r.error || '无结果'))
      state.value = 'listening'
    }
  } catch (e) {
    console.error('[Asst] transcribe error:', e)
    addMessage('system', '转写异常：' + formatError(e))
    state.value = 'error'
  }
}

/** 开启/关闭唤醒。Toggle wake word detection on/off.
 *  副作用：修改状态、加载模型、启动/停止引擎。Side effects: modify state, load model, start/stop engine. */
export async function toggleWake() {
  console.log('[Asst] toggleWake called, current state:', state.value, 'modelLoaded:', modelLoaded)
  statusLine.value = ''

  if (state.value === 'idle' || state.value === 'done' || state.value === 'error') {
    // 开启。Enable.
    if (typeof WakeWordEngine === 'undefined') {
      console.error('[Asst] WakeWordEngine not defined')
      failWake('唤醒引擎未加载，请刷新页面重试')
      return
    }

    if (!modelLoaded) {
      statusLine.value = '正在加载语音模型...'
      state.value = 'listening' // 先切到 listening 让用户看到变化。Switch to listening first for user feedback.
      console.log('[Asst] loading model...')
      try {
        const ok = await initWakeModel()
        if (!ok) {
          console.error('[Asst] model init failed')
          failWake('语音模型加载失败，请刷新页面重试')
          return
        }
      } catch (e) {
        console.error('[Asst] model init exception:', e)
        failWake('语音模型加载异常：' + formatError(e))
        return
      }
    }

    statusLine.value = '正在启动唤醒...'
    console.log('[Asst] starting WakeWordEngine...')

    // 预检麦克风设备：无可用录音设备时提前提示，避免模糊的 NotFoundError。
    // Pre-check microphone devices: prompt early when no recording device available, avoid ambiguous NotFoundError.
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
      // start() 内部会 catch 错误并返回 false（如麦克风被系统/浏览器拦截），需检查返回值。
      // start() internally catches errors and returns false (e.g., mic blocked by system/browser), need to check return value.
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
    // 关闭。Disable.
    console.log('[Asst] stopping...')
    try { WakeWordEngine.stop() } catch (e) { console.error('[Asst] stop error:', e) }
    wakeEnabled.value = false
    state.value = 'idle'
    partialText.value = ''
    statusLine.value = ''
  }
}

/** 页面销毁时收尾：停唤醒、清定时器、停录音。
 *  Cleanup on page destruction: stop wake, clear timers, stop recording. */
export function stopWake() {
  try { WakeWordEngine.stop() } catch { /* ignore */ }
  clearTimers()
  if (wakeRecorder && wakeRecorder.state !== 'inactive') {
    try { wakeRecorder.stop() } catch { /* ignore */ }
  }
}

/**
 * 播报期间暂停唤醒引擎；播完按上下文恢复 —— 这是每次播报的两端。
 *
 * 暂停：消除助手自己的声音自触发唤醒（echoCancellation 只能缓解，不能消除）。
 * 恢复：若此时有待答提问 → 自动开录等待作答（不必再说唤醒词）；否则恢复监听。
 *
 * 引擎只有 stop/start、没有 pause；stop() 释放麦克风轨道、start() 只重建流与
 * recognizer（**不重载 42MB 模型**），故成本可接受。注意开录依赖引擎的麦克风流，
 * 故必须先确认引擎在运行再开录。
 *
 * Pause the wake engine during playback and restore it afterwards — the two ends of every
 * utterance. Pausing stops the assistant's own voice from self-triggering the wake word
 * (echoCancellation only mitigates that). On restore, a pending question auto-starts
 * recording for the answer (no wake word needed); otherwise listening resumes. The engine
 * offers stop/start but no pause: stop() releases the mic track and start() only rebuilds
 * the stream and recognizer (**no 42MB model reload**). Recording needs the engine's mic
 * stream, so the engine must be confirmed running before recording starts.
 */
watch(speaking, (isSpeaking) => {
  const eng = (globalThis as { WakeWordEngine?: any }).WakeWordEngine
  if (!eng) return

  if (isSpeaking) {
    // 播报开始：暂停监听（未运行则是无操作）。
    if (eng.isRunning?.()) eng.stop()
    return
  }

  // 播报结束。
  const q = pendingQuestion.value
  if (q) {
    const ns = nextState(state.value, 'question_ready')
    if (ns !== 'awaiting_answer') return
    state.value = ns
    const begin = () => {
      if (!startRecording(answerTimeoutMs())) state.value = 'listening'
    }
    if (eng.isRunning?.()) begin()
    else void Promise.resolve(eng.start?.()).then(begin)   // 先重启引擎拿到麦克风流
    return
  }

  // 无待答提问：恢复监听（仅在唤醒开关打开时，避免「关了唤醒却被动开麦」）。
  if (wakeEnabled.value && eng.isModelLoaded?.() && !eng.isRunning?.()) void eng.start()
})
