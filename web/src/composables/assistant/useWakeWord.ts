import { watch } from 'vue'
import { api } from '../../api'
import { nextState } from './wakeFsm'
import { speaking } from './useTts'
import { state, partialText, statusLine, wakeEnabled, vadConfig, pendingQuestion, failWake } from './store'
import { createSegmentRecorder, type SegmentRecorder } from './useSegmentRecorder'
import { sendText, sendAnswer } from './useChat'
import { matchOption } from './answerMatch'

/**
 * 唤醒链路（VAD 驱动，云端判定）。
 *
 * 本地常驻 VAD 把「疑似人声」切成分段并上传 `/api/voice/wake`，后端负责转写与唤醒词判定，
 * 前端只按 `{matched, command}` 行事：
 *   - 命中且带指令 → 直接起一轮（省掉「提示音 + 再录一次 + 再转写」）
 *   - 只命中唤醒词 → 提示音后把**下一段**当指令
 *   - 不命中 → 丢弃
 *
 * 待答提问优先：有待答提问时每一段都是**回答**，绝不送去判唤醒词（否则用户的回答会被
 * 当成不含唤醒词的噪音丢掉，语音作答静默失效）。
 *
 * Wake pipeline (VAD-driven, judgement in the cloud).
 *
 * The always-on local VAD cuts speech into segments and uploads them to `/api/voice/wake`; the
 * backend transcribes and judges the wake word, and the frontend only acts on `{matched, command}`:
 * a hit with a command starts a turn immediately (skipping "chime, record again, transcribe
 * again"), a bare hit chimes and treats the *next* segment as the command, and a miss is dropped.
 *
 * A pending question wins: while one is open, every segment is an *answer* and must never go to
 * wake detection, or the answer would be discarded as noise that carries no wake word.
 */

/** 常驻分段录音器（麦克风流由本模块持有）。The always-on segment recorder (this module owns the mic stream). */
let segmenter: SegmentRecorder | null = null
/** 当前麦克风流；暂停监听时会释放轨道。The current mic stream; its tracks are released while listening is paused. */
let micStream: MediaStream | null = null
/** 仅听到唤醒词后置位：下一段直接当指令，不再判唤醒词。
 *  Set only after a bare wake word: the next segment is the command and skips wake detection. */
let awaitingCommand = false
/** 连续上传失败次数，达阈值熔断。Consecutive upload failures; the circuit breaks at the threshold. */
let failures = 0
/** 熔断阈值（写死为 3：先看实际表现再决定要不要做成配置）。
 *  Circuit-break threshold (hard-coded to 3 until real-world behaviour says otherwise). */
const FAILURE_LIMIT = 3
/** 上一次唤醒检测上传的时间戳（节流用）。Timestamp of the last wake-detection upload (throttling). */
let lastUploadAt = 0
/**
 * 监听代际：stopListening() 每次递增。取流是异步的，若在它返回前又被暂停，代际就对不上 ——
 * 迟到的那条流必须当场释放，否则播报期间麦克风复活、助手的声音会自触发唤醒。
 *
 * Listening generation, bumped by every stopListening(). Acquisition is async: if a pause lands
 * before it returns, the generation no longer matches — the late stream must be released on the
 * spot, or the mic revives mid-playback and the assistant's own voice can wake it.
 */
let listenGen = 0

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

/** 上传失败累计与熔断提示。Count upload failures and surface the circuit break. */
function onUploadFailed() {
  failures++
  if (failures >= FAILURE_LIMIT) {
    // spec「错误与降级」：云端不可用必须**明确提示**，不静默失败 ——
    // 否则用户只看到「唤醒突然不灵了」，无从判断原因。
    // Spec, "errors and degradation": an unavailable cloud must be surfaced explicitly, never
    // fail silently — otherwise the user only sees "waking suddenly stopped working".
    statusLine.value = '⚠️ 云端唤醒不可用（已连续失败 3 次）· 可双击悬浮球手动触发'
    console.warn('[wake] 连续失败达阈值，已暂停上传')
  }
}

/**
 * 转写一段音频；失败计一次失败次数并给出空串。
 * Transcribe one segment; a failure counts towards the circuit breaker and yields ''.
 *
 * @param blob 一段音频。One audio segment.
 * @returns 去空白后的转写文本，失败/空结果为空串。The trimmed transcript, or '' on failure/empty.
 */
async function transcribeSegment(blob: Blob): Promise<string> {
  try {
    const r = await api.transcribe(blob)
    return (r?.text || '').trim()
  } catch {
    onUploadFailed()
    return ''
  }
}

/** 处理一段音频：先看是不是在回答问题，否则做唤醒检测。导出供测试。
 *  Handle one audio segment: an answer first, wake detection otherwise. Exported for tests.
 *
 *  本函数是 async，内部异常只会变成 rejected promise，**不会同步抛回** onSegment 的调用方
 *  （useSegmentRecorder.finishSegment），因此不可能打断 recorder 内部复位；调用处另加
 *  catch 兜住 unhandled rejection。
 *
 *  This function is async, so its internal throws become a rejected promise and can never
 *  propagate synchronously back into the caller of onSegment (useSegmentRecorder.finishSegment),
 *  so the recorder's internal reset cannot be skipped; the call site adds a catch for unhandled
 *  rejections anyway.
 *
 *  @param blob 一段音频。One audio segment.
 */
export async function handleSegment(blob: Blob) {
  // 熔断：连续失败后停止上传，避免疯狂重试烧钱。
  // Circuit break: stop uploading after consecutive failures instead of burning money on retries.
  if (failures >= FAILURE_LIMIT) return

  // ⚠️ 待答提问优先：这一段是**回答**，绝不能送去判唤醒词 ——
  // 否则用户答「允许本次」，会被当成不含唤醒词的噪音丢掉，P6 的语音作答就此失效。
  //
  // A pending question wins: this segment is an *answer* and must never go to wake detection, or
  // answering "允许本次" would be dropped as noise with no wake word in it and P6's voice
  // answering would die.
  //
  // 判据是「有没有待答提问」，不是「处于哪个状态」：关闭播报（speakEnabled=false）时
  // speaking 从不翻转为 true，状态会停在提问时的 thinking，若再按状态收窄，回答就会被丢掉 ——
  // 而语音作答静默失效正是本任务最怕的错。
  //
  // The test is "is a question pending", not "which state are we in": with playback muted
  // (speakEnabled=false) `speaking` never flips, the state stays at the `thinking` set when the
  // question arrived, and narrowing by state would drop the answer — the exact silent failure
  // this task warns about.
  const pq = pendingQuestion.value
  if (pq) {
    const text = await transcribeSegment(blob)
    if (!text) return
    failures = 0
    // 精确匹配到选项则回传该选项的 value，否则整段作为文本作答（与旧 handleTranscript 同规则）。
    // An exact option match returns that option's value; anything else is the whole text as a free
    // answer (the same rule the old handleTranscript used).
    const hit = matchOption(text, pq.options)
    await sendAnswer(hit ? '' : text, hit?.value)
    return
  }

  // 刚听到唤醒词、正在等指令：这一段直接当指令，不再判唤醒词。
  // A wake word was just heard and the command is awaited: this segment *is* the command, no
  // wake detection for it.
  if (awaitingCommand) {
    awaitingCommand = false
    const text = await transcribeSegment(blob)
    if (text) { failures = 0; sendText(text) }
    return
  }

  // 节流只加在「判唤醒词」这条路径上：它拦的是误触发时的付费上传，而答案与指令通道
  // 是用户明确说出的内容 —— 若一起节流，刚说完唤醒词就开口的用户会被自己的节流丢掉。
  // The throttle guards the wake-detection path only: it exists to stop a false trigger from
  // hammering the paid endpoint, while the answer and command channels carry what the user
  // deliberately said — throttling those would drop the speech right after a bare wake word.
  const now = Date.now()
  if (now - lastUploadAt < vadConfig.upload_throttle_ms) return
  lastUploadAt = now

  let r: Awaited<ReturnType<typeof api.wakeDetect>> | undefined
  try {
    r = await api.wakeDetect(blob)
  } catch {
    onUploadFailed()
    return
  }
  if (!r?.ok) { onUploadFailed(); return }
  failures = 0
  statusLine.value = ''

  if (!r.matched) return                          // 噪音/无关对话 → 丢弃。Noise/unrelated talk → dropped.
  if (r.command) { sendText(r.command); return }  // 唤醒词 + 指令 → 直接起一轮。Wake word plus command → a turn.
  awaitingCommand = true                          // 仅唤醒词 → 提示音后等下一段。Bare wake word → chime, then wait.
  playBeep()
}

/**
 * 用当前麦克风流建一个分段录音器并启动。
 * Build a segment recorder on the current mic stream and start it.
 *
 * 每次恢复监听都**新建**实例而不复用旧的：旧实例 stop() 时冲出的在途段会走它的
 * onstop（异步），复用会让那次迟到的收尾改写新实例的记账 —— 孤立一台活着的 recorder，
 * 此后永不停止。新建实例则让迟到回调只能改到它自己（且其 suppressed 仍为 true，不会再上传）。
 *
 * A **fresh** instance is built on every resume, never a reused one: the in-flight segment a
 * stop() cuts loose settles through the old instance's asynchronous onstop, and reusing it would
 * let that late settlement rewrite the new instance's bookkeeping — orphaning a live recorder that
 * then never stops. A fresh instance confines the late callback to the old closure (whose
 * `suppressed` is still true, so it cannot emit either).
 */
function startSegmenter() {
  if (!micStream) return
  segmenter = createSegmentRecorder(micStream, {
    speechThreshold: vadConfig.silence_threshold,
    silenceMs: vadConfig.silence_duration_ms,
    minSpeechMs: vadConfig.min_speech_ms,
    maxMs: vadConfig.max_duration_ms,
    onSegment: (b) => {
      // handleSegment 的异常只会变成 rejected promise（不会同步抛回 recorder 的收尾路径），
      // 这里再兜一层，避免它变成 unhandled rejection。
      // handleSegment's throws only become a rejected promise (they cannot propagate back into the
      // recorder's settling path); this catch keeps them from turning into unhandled rejections.
      void handleSegment(b).catch((e) => console.warn('[Asst] handleSegment error:', e))
    },
  })
  segmenter.start()
}

/**
 * 停掉分段录音器并释放麦克风轨道。
 * Stop the segment recorder and release the mic tracks.
 *
 * 即使当前什么都没在跑也要推进代际 —— 可能有 getUserMedia 在途（见 listenGen 的说明）。
 * The generation advances even when nothing is running, because an acquisition may be in flight
 * (see listenGen).
 *
 * 同时清掉 `awaitingCommand`：暂停/关闭之后用户并没有在说指令，不能让下一段被误当指令。
 * It also clears `awaitingCommand`: after a pause or a shutdown the user is not mid-command, so the
 * next segment must not be mistaken for one.
 */
function stopListening() {
  listenGen++
  awaitingCommand = false
  if (segmenter) {
    try { segmenter.stop() } catch (e) { console.error('[Asst] segmenter stop error:', e) }
    segmenter = null
  }
  if (micStream) {
    try { micStream.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    micStream = null
  }
}

/**
 * 确保常驻监听在跑：没有录音器时重新取流并新建一个。
 * Ensure always-on listening is running: re-acquire the stream and build a recorder when there is none.
 *
 * @returns 是否正在监听。Whether listening is running.
 */
async function ensureListening(): Promise<boolean> {
  if (!wakeEnabled.value || segmenter) return false
  const gen = listenGen
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
  } catch (e) {
    // 这里刻意不走 failWake：它会把状态置为 error、弹开面板并写一条醒目错误，而此刻用户
    // 很可能正等着回答提问 —— 取流失败只该在状态行提示，不该把「待答」冲掉。
    // Deliberately not failWake: it forces state to `error`, expands the panel and posts a loud
    // message, and the user is likely mid-answer — a failed acquisition should surface a hint on
    // the status line, not clobber the awaiting state.
    console.warn('[Asst] resume listening failed:', e)
    statusLine.value = describeMicError(e)
    return false
  }
  if (gen !== listenGen) {
    // 等待期间又被暂停了（播报开始 / 关掉唤醒）：这条流已经不该存在，当场释放。
    // A pause landed while acquisition was in flight (playback started, wake switched off): this
    // stream should not exist any more, so release it on the spot.
    try { stream.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
    return false
  }
  micStream = stream
  try {
    startSegmenter()
  } catch (e) {
    // 起不来就当场收干净：留着一条活的 micStream 而 VAD 没在跑，就是「麦克风被占着却谁也不听」
    // 的静默故障（本重构要修的那一类），宁可退回未监听。
    // If it cannot start, tidy up on the spot: a live micStream with a dead VAD is exactly the
    // silent "mic held open but nobody listening" failure this rework exists to remove, so fall
    // back to not listening.
    console.error('[Asst] segmenter start failed:', e)
    stopListening()
    return false
  }
  return true
}

/** 开启/关闭唤醒。Toggle wake word detection on/off.
 *  副作用：修改状态、取麦克风、起停分段录音器。
 *  Side effects: modify state, acquire the microphone, start/stop the segment recorder. */
export async function toggleWake() {
  console.log('[Asst] toggleWake called, current state:', state.value)
  statusLine.value = ''

  if (state.value === 'idle' || state.value === 'done' || state.value === 'error') {
    // 开启。Enable.
    statusLine.value = '正在启动唤醒...'

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
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
    } catch (e: any) {
      console.error('[Asst] getUserMedia failed:', e)
      failWake(describeMicError(e))
      return
    }
    startSegmenter()
    wakeEnabled.value = true
    state.value = 'listening'
    statusLine.value = ''
    console.log('[Asst] listening started!')
  } else {
    // 关闭。Disable.
    console.log('[Asst] stopping...')
    stopListening()
    wakeEnabled.value = false
    state.value = 'idle'
    partialText.value = ''
    statusLine.value = ''
  }
}

/** 页面销毁时收尾：停监听、释放麦克风。
 *  Cleanup on page destruction: stop listening and release the microphone. */
export function stopWake() {
  stopListening()
}

/**
 * 播报期间暂停监听；播完按上下文恢复 —— 这是每次播报的两端。
 *
 * 暂停：消除助手自己的声音自触发唤醒（echoCancellation 只能缓解，不能消除）；顺带把麦克风
 * 轨道也放掉，播报期间麦克风是真的关着。
 * 恢复：若此时有待答提问 → 自动回到待答（不必再说唤醒词）；否则恢复聆听。
 * 两侧都不复用旧录音器：恢复一律重新取流 + 新建（理由见 startSegmenter）。
 *
 * Pause the wake listener during playback and restore it afterwards — the two ends of every
 * utterance. Pausing stops the assistant's own voice from self-triggering the wake word
 * (echoCancellation only mitigates that) and releases the mic tracks, so the mic is genuinely off
 * while the assistant speaks. On restore, a pending question returns to awaiting_answer (no wake
 * word needed); otherwise listening resumes. Neither side reuses the old recorder: a resume always
 * re-acquires the stream and builds a fresh one (see startSegmenter).
 */
watch(speaking, (isSpeaking) => {
  if (isSpeaking) {
    // 播报开始：暂停监听（没在跑也要推进代际，见 stopListening）。
    // Playback starts: pause listening (the generation advances even when nothing is running).
    stopListening()
    return
  }

  // 播报结束。Playback ended.
  const q = pendingQuestion.value
  if (q) {
    const ns = nextState(state.value, 'question_ready')
    if (ns !== 'awaiting_answer') return
    state.value = ns
    void ensureListening()
    return
  }

  // 无待答提问：恢复监听（仅在唤醒开关打开时，避免「关了唤醒却被动开麦」）。
  // No pending question: resume listening, and only while wake is enabled, so switching wake off
  // never leaves a live mic behind.
  if (wakeEnabled.value) void ensureListening()
})
