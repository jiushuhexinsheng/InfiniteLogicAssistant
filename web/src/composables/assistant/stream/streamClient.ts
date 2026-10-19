/**
 * 浏览器麦克风 → AudioWorklet → WebSocket 流式客户端。
 *
 * Browser mic → AudioWorklet → WebSocket streaming client.
 *
 * 一条连接对应一路麦克风：`start` 取流、建 AudioContext/Worklet、连上
 * `/api/voice/asr/stream` 并发 `start`；之后每个 20 ms 帧以二进制发送。
 * 服务端事件（ready/vad/partial/final/error）原样交给 `onEvent`。
 *
 * One connection owns one microphone: `start` acquires the stream, builds the
 * AudioContext/Worklet, connects `/api/voice/asr/stream` and sends `start`; each
 * 20 ms frame then goes out as a binary message. Server events (ready/vad/partial/
 * final/error) are handed to `onEvent` verbatim.
 */
export interface VoiceStreamEvent {
  type: string
  [key: string]: unknown
}

export interface VoiceStreamOptions {
  onEvent: (event: VoiceStreamEvent) => void
  onLevel?: (rms: number) => void
  onError?: (error: Error) => void
  onClose?: () => void
  /** 浏览器 deviceId；空 = 系统默认。Browser deviceId; empty = system default. */
  inputDevice?: string
  echoCancellation?: boolean
  noiseSuppression?: boolean
  autoGain?: boolean
}

export interface VoiceStreamHandle {
  start(): Promise<void>
  stop(): void
  send(message: Record<string, unknown>): void
  /** 暂停/恢复发送（TTS 播报时抑制回声）。Pause/resume sending (TTS echo guard). */
  setMuted(muted: boolean): void
  isRunning(): boolean
}

/** 帧长（毫秒），与服务端默认一致。Frame length in ms, matching the server default. */
const FRAME_MS = 20

/**
 * 创建流式语音客户端（每次开麦创建一个；停麦即释放）。
 * Create a streaming voice client (one per listening session; released on stop).
 */
export function createVoiceStream(opts: VoiceStreamOptions): VoiceStreamHandle {
  let ws: WebSocket | null = null
  let ctx: AudioContext | null = null
  let media: MediaStream | null = null
  let node: AudioWorkletNode | null = null
  let running = false
  let muted = false

  const constraints = (withDevice: boolean): MediaStreamConstraints => ({
    audio: {
      channelCount: 1,
      echoCancellation: opts.echoCancellation ?? true,
      noiseSuppression: opts.noiseSuppression ?? true,
      autoGainControl: opts.autoGain ?? true,
      // 16 kHz 是理想值；浏览器可以拒绝，实际采样率从 AudioContext 读。
      // 16 kHz is the ideal; the browser may refuse, so the real rate comes from AudioContext.
      sampleRate: { ideal: 16000 },
      ...(withDevice && opts.inputDevice ? { deviceId: { exact: opts.inputDevice } } : {}),
    },
  })

  async function acquire(): Promise<MediaStream> {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints(true))
    } catch (e) {
      if (!opts.inputDevice) throw e
      // 所选设备拔掉/被占用：回退默认设备并让上层给可见提示。
      // The chosen device vanished/busy: fall back to the default and tell the caller.
      opts.onError?.(new Error('所选麦克风不可用，已回退系统默认设备'))
      return navigator.mediaDevices.getUserMedia(constraints(false))
    }
  }

  async function start(): Promise<void> {
    if (running) return
    media = await acquire()

    try {
      ctx = new AudioContext({ sampleRate: 16000 })
    } catch {
      ctx = new AudioContext()
    }
    // 静态资源放在 web/public，避免被 Vite 内联成 data URL（部分浏览器拒绝 worklet data URL）。
    // Served from web/public so Vite cannot inline it as a data URL (some browsers reject those).
    await ctx.audioWorklet.addModule('/frame-processor.js')
    await ctx.resume()

    const source = ctx.createMediaStreamSource(media)
    const frameSize = Math.max(1, Math.round(ctx.sampleRate * FRAME_MS / 1000))
    node = new AudioWorkletNode(ctx, 'frame-processor', { processorOptions: { frameSize } })
    node.port.onmessage = (ev: MessageEvent) => {
      const data = ev.data as { pcm: ArrayBuffer; rms: number }
      opts.onLevel?.(data.rms)
      if (!muted && ws && ws.readyState === WebSocket.OPEN) {
        try { ws.send(data.pcm) } catch { /* 连接刚断，丢一帧 */ }
      }
    }
    source.connect(node)
    // 无输出也要接到 destination 才会被音频图拉取；processor 不写输出 → 静音。
    // Connect to destination so the graph pulls it; the processor writes no output → silence.
    node.connect(ctx.destination)

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/api/voice/asr/stream`)
    await new Promise<void>((resolve, reject) => {
      if (!ws) { reject(new Error('WebSocket 未创建')); return }
      ws.onopen = () => resolve()
      ws.onerror = () => reject(new Error('语音流连接失败'))
    })
    ws.onmessage = (ev) => {
      try {
        opts.onEvent(JSON.parse(ev.data) as VoiceStreamEvent)
      } catch { /* 非 JSON 帧忽略 */ }
    }
    ws.onclose = () => {
      running = false
      // 服务端关闭/报错时也要释放麦克风与音频图，否则麦克风会一直占着。
      // Release the mic and audio graph on a server close/error too; otherwise the mic stays held.
      releaseAudio()
      opts.onClose?.()
    }
    ws.onerror = () => opts.onError?.(new Error('语音流连接错误'))
    ws.send(JSON.stringify({
      type: 'start',
      sample_rate: ctx.sampleRate,
      channels: 1,
      format: 'pcm_s16le',
    }))
    running = true
  }

  function releaseAudio(): void {
    if (node) {
      try { node.port.onmessage = null } catch { /* ignore */ }
      try { node.disconnect() } catch { /* ignore */ }
      node = null
    }
    if (media) {
      try { media.getTracks().forEach((t) => t.stop()) } catch { /* ignore */ }
      media = null
    }
    if (ctx) {
      try { void ctx.close() } catch { /* ignore */ }
      ctx = null
    }
    opts.onLevel?.(0)
  }

  function stop(): void {
    running = false
    try { ws?.send(JSON.stringify({ type: 'stop' })) } catch { /* ignore */ }
    try { ws?.close() } catch { /* ignore */ }
    ws = null
    releaseAudio()
  }

  return {
    start,
    stop,
    send(message) {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message))
    },
    setMuted(value) {
      muted = value
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: value ? 'mute' : 'unmute' }))
      }
    },
    isRunning: () => running,
  }
}
