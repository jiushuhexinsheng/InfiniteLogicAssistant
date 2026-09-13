/**
 * 常驻 VAD + 分段录音。
 *
 * 为什么要单独一个模块：唤醒链路改成「VAD 驱动录音」后，VAD 不再是录音的附属（旧代码里
 * 它跟着 MediaRecorder 起停），而是**驱动方** —— 它决定一段从哪里开始、到哪里结束，以及
 * 这一段值不值得上传。把这个决策单独成模块，才能脱离浏览器音频栈单测。
 *
 * Always-on VAD driving segment recording. Extracted because the wake pipeline now has the VAD
 * **drive** recording rather than tag along with it (in the old code it started and stopped with
 * the MediaRecorder): the VAD decides where a segment begins and ends, and whether it is worth
 * uploading at all. Isolating that decision is what makes it testable without a real audio stack.
 */

/** 分段录音的参数。Segment-recording options. */
export interface SegmentOptions {
  /** 判定为「有人在说」的 RMS 阈值（0..1）。RMS threshold above which someone is speaking. */
  speechThreshold: number
  /** 静音多久算一段说完（毫秒）。Silence duration that ends a segment, in ms. */
  silenceMs: number
  /** 短于此长度的段直接丢弃、不上传（毫秒）。Segments shorter than this are dropped, never uploaded. */
  minSpeechMs: number
  /** 单段硬上限（毫秒）。Hard cap on one segment, in ms. */
  maxMs: number
  /** 一段就绪时回调（已过滤掉过短的段）。Called with a finished segment, short ones already filtered. */
  onSegment: (blob: Blob) => void
}

/** 分段录音句柄。The segment recorder handle. */
export interface SegmentRecorder {
  /** 开始常驻监听。Start listening. */
  start(): void
  /** 停止并释放。Stop and release. */
  stop(): void
  /** 当前是否正在录一段。Whether a segment is being recorded right now. */
  isRecording(): boolean
}

/** VAD 检查周期（毫秒）。VAD check interval in ms. */
const CHECK_MS = 100

/**
 * 创建一个分段录音器。
 * Create a segment recorder.
 *
 * @param stream 麦克风流（与录音共用同一条流）。The mic stream (shared with recording).
 * @param opts 参数。Options.
 * @returns 句柄。The handle.
 */
export function createSegmentRecorder(stream: MediaStream, opts: SegmentOptions): SegmentRecorder {
  let ctx: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  let recorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  let recording = false
  /** 本段内是否已检测到语音（用于 minSpeechMs 判定）。Whether speech was seen in this segment. */
  let speechSeen = false
  /** 已检测到语音的累计时长（毫秒）。Accumulated speech duration in ms. */
  let speechMs = 0
  let silenceCount = 0
  let elapsed = 0
  /** stop() 之后是否屏蔽回调。Whether callbacks are suppressed after stop(). */
  let suppressed = false

  /**
   * 复位当前段的记账状态。
   * Reset the current segment's bookkeeping.
   *
   * 不变量：**任何结束一段的路径都必须走到这里**。只靠 onstop 收尾是不够的 —— 构造失败、
   * 以及 endSegment() 撞上「recorder 不存在 / 不在 recording 状态」这两条路径都不会触发
   * onstop，speechSeen 会永久停在 true，此后 `if (!speechSeen)` 永远为假、beginSegment 再也
   * 不被调用，分段彻底停摆（与本次重构要修的原故障同型）。
   * Invariant: **every path that ends a segment must pass through here.** Settling only in onstop
   * is not enough: a failed constructor, and endSegment() meeting a recorder that is missing or not
   * in the recording state, never fire onstop — speechSeen then stays true forever, `if (!speechSeen)`
   * is never true again, beginSegment is never called, and segmentation dies permanently.
   */
  function resetSegment() {
    speechSeen = false
    speechMs = 0
    chunks = []
    recorder = null
    recording = false
  }

  /**
   * onstop 收尾：按 minSpeechMs 决定是否回调，然后复位。
   * onstop tail: emit unless the segment is too short, then reset.
   */
  function finishSegment() {
    const blob = new Blob(chunks, { type: 'audio/webm' })
    // 过短的段不上传：这是省调用量的第一道闸，VAD 已判过静音，这里再滤爆音。
    // stop() 之后也不再回调：用户已经关掉唤醒了，在途的那段应当丢弃。
    // Too-short segments are never uploaded: this is the first cost gate, on top of the VAD's
    // silence filtering, and it removes coughs and door slams. Nothing is emitted after stop()
    // either: the user turned wake off, so an in-flight segment is dropped.
    if (!suppressed && speechMs >= opts.minSpeechMs && blob.size > 0) opts.onSegment(blob)
    resetSegment()
  }

  function beginSegment() {
    chunks = []
    let mime = 'audio/webm'
    if (!MediaRecorder.isTypeSupported(mime)) {
      mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''
    }
    let rec: MediaRecorder
    try {
      rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
      rec.onstop = () => finishSegment()
      rec.start()
    } catch {
      // 构造/启动失败：这一段作废，但**必须**复位记账状态 —— 否则不会有 onstop 来收尾，
      // speechSeen 卡在 true，后续语音再也切不出段（永久停摆）。
      // Construction/startup failed: drop this segment, but **must** reset the bookkeeping —
      // no onstop will come to settle it, so speechSeen would stick at true and all later speech
      // would be unable to start a segment (a permanent stall).
      resetSegment()
      return
    }
    recorder = rec
    recording = true
    // 注意：**不要**在这里重置 speechSeen / speechMs —— 调用方紧接着就会置 speechSeen=true
    // 并累加 speechMs，在此清零会让首帧统计丢失（顺序敏感的陷阱）。这两个变量由 resetSegment 复位。
    // Do **not** reset speechSeen / speechMs here: the caller sets speechSeen and accumulates
    // speechMs immediately after this returns, so clearing them here would drop the first frame's
    // tally (an order-sensitive trap). resetSegment clears them when the segment settles.
    silenceCount = 0
    elapsed = 0
  }

  function endSegment() {
    recording = false
    const rec = recorder
    if (rec && rec.state === 'recording') {
      // 交给 onstop → finishSegment 收尾并按 minSpeechMs 判定。
      // Hand off to onstop → finishSegment, which applies the minSpeechMs gate.
      rec.stop()
      return
    }
    // 没有 live recorder：不会有 onstop 来收尾，就地复位（不变量）。
    // No live recorder: no onstop will come, so reset in place (the invariant).
    resetSegment()
  }

  function tick() {
    if (!analyser) return
    elapsed += CHECK_MS
    const buf = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(buf)
    let sum = 0
    for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v }
    const rms = Math.sqrt(sum / buf.length)

    if (rms >= opts.speechThreshold) {
      silenceCount = 0
      if (!speechSeen) { speechSeen = true; if (!recording) beginSegment() }
      speechMs += CHECK_MS
    } else {
      if (!speechSeen) return                 // 还没开口，什么都不做
      silenceCount += CHECK_MS
      if (silenceCount >= opts.silenceMs) endSegment()
    }

    if (recording && elapsed >= opts.maxMs) endSegment()
  }

  return {
    start() {
      if (timer) return
      suppressed = false                     // 重新监听：解除 stop() 的屏蔽
      try {
        ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
        const source = ctx.createMediaStreamSource(stream)
        analyser = ctx.createAnalyser()
        analyser.fftSize = 2048
        analyser.smoothingTimeConstant = 0.3
        source.connect(analyser)
      } catch { return }
      timer = setInterval(tick, CHECK_MS)
    },
    stop() {
      if (timer) { clearInterval(timer); timer = null }
      // 先屏蔽再收尾：stop() 冲出的在途段不上传（用户已经关掉唤醒了）。复位照旧发生。
      // Suppress before settling: an in-flight segment is never uploaded after stop() (wake is
      // off). The bookkeeping is still reset.
      suppressed = true
      if (recording) endSegment()
      analyser = null
      if (ctx) { try { ctx.close() } catch { /* ignore */ } ctx = null }
    },
    isRecording: () => recording,
  }
}
