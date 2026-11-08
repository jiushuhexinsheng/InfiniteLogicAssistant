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
import { withTokenParam } from '../../../api/auth'
import { createPreopenQueue } from './preopenQueue'

export interface VoiceStreamEvent {
  type: string
  [key: string]: unknown
}

/** 关闭事件信息。Close info. */
export interface VoiceStreamCloseInfo {
  /** 客户端是否会自动重连（true 时调用方应保留 handle，不要丢弃）。
   *  Whether the client will retry automatically (keep the handle when true). */
  willReconnect: boolean
}

export interface VoiceStreamOptions {
  onEvent: (event: VoiceStreamEvent) => void
  onLevel?: (rms: number) => void
  onError?: (error: Error) => void
  onClose?: (info: VoiceStreamCloseInfo) => void
  /** 浏览器 deviceId；空 = 系统默认。Browser deviceId; empty = system default. */
  inputDevice?: string
  echoCancellation?: boolean
  noiseSuppression?: boolean
  autoGain?: boolean
  /** 建连时的初始闸门（缺省 wake）。Initial gate at connect time (default wake). */
  gate?: StreamGate
}

/** 服务端上传闸门：wake = 等待唤醒词（KWS 未命中不上云）；open = 免唤醒开放聆听。
 *  Server upload gate: wake = waiting for the wake word (KWS miss never uploads);
 *  open = wake-free continuous listening. */
export type StreamGate = 'wake' | 'open'

export interface VoiceStreamHandle {
  start(): Promise<void>
  stop(): void
  send(message: Record<string, unknown>): void
  /** 暂停/恢复发送（TTS 播报时抑制回声）。Pause/resume sending (TTS echo guard). */
  setMuted(muted: boolean): void
  /** 切换服务端上传闸门（连接未就绪时记住，连通后补发）。
   *  Switch the server upload gate (remembered and sent once connected). */
  setGate(mode: StreamGate): void
  isRunning(): boolean
}

/** 帧长（毫秒），与服务端默认一致。Frame length in ms, matching the server default. */
const FRAME_MS = 20

/** 断线重连的指数退避：500ms 起翻倍，封顶 15s。
 *  Reconnect backoff: 500ms doubling, capped at 15s. */
const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 15_000

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
  // 上传闸门（wake/open）：连接未 OPEN 时先记住，start 发出后立刻补发（在补发预开帧之前）。
  // Upload gate (wake/open): remembered until the socket is OPEN, flushed right after
  // start and before the pre-open frames (so the first segment is gated correctly).
  let gate: StreamGate = opts.gate ?? 'wake'
  // WS OPEN / start 发出之前产生的帧先进队列，连通后补发（避免吞掉首字）。
  // Frames produced before WS OPEN / before `start` go to the queue and are flushed
  // once connected (so the first syllable is not dropped).
  const preopen = createPreopenQueue()
  let preopenActive = false
  let started = false
  // 断线重连状态（docs/designs/10 4.5）：
  // gen 在每次 start/stop 递增，用作代际号 —— 旧连接/旧重连定时器的回调先比对代际，
  // 不得动新连接；stopped 是「用户主动停止」，为 true 时一律不重连。
  // Reconnect state: `gen` increments on every start/stop as the generation counter —
  // callbacks from an old socket or an old retry timer compare it before touching the
  // new connection; `stopped` means "user stopped" and suppresses all retries.
  let gen = 0
  let stopped = false
  let readyOnce = false
  let serverFailed = false
  let reconnectAttempt = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  /** 启动中途被 stop() 时用来拒绝 ready 等待（否则 start() 永久挂起）。
   *  Rejects the ready wait when stop() lands mid-start (otherwise start() hangs). */
  let cancelStart: ((e: Error) => void) | null = null

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

  function sendGate(): void {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify({ type: 'gate', mode: gate })) } catch { /* 连接刚断 */ }
    }
  }

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
    // 认领代际 + 清除「主动停止」标志：本次启动之后的一切回调只看这个代际。
    // Claim the generation and clear the stop flag: every callback below keys off it.
    const myGen = ++gen
    stopped = false
    serverFailed = false
    readyOnce = false
    preopen.clear()
    preopenActive = false
    started = false
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
      if (muted) return
      if (started && ws && ws.readyState === WebSocket.OPEN) {
        try { ws.send(data.pcm) } catch { /* 连接刚断，丢一帧 */ }
      } else if (preopenActive) {
        // 尚未连通 / start 还没发出：先缓存。Not connected yet / start not sent: buffer.
        preopen.push(data.pcm)
      }
    }
    // 先允许缓存再接通音频图：worklet 从 connect 起就开始产帧。
    // Allow buffering before wiring the graph: the worklet starts emitting at connect.
    preopenActive = true
    source.connect(node)
    // 无输出也要接到 destination 才会被音频图拉取；processor 不写输出 → 静音。
    // Connect to destination so the graph pulls it; the processor writes no output → silence.
    node.connect(ctx.destination)

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    // WS 无法自定义请求头：token 走查询参数（服务端两种都接受）。
    // WS cannot set custom headers: carry the token in the query (the server accepts both).
    ws = new WebSocket(withTokenParam(`${proto}://${location.host}/api/voice/asr/stream`))
    await new Promise<void>((resolve, reject) => {
      if (!ws) { reject(new Error('WebSocket 未创建')); return }
      ws.onopen = () => resolve()
      ws.onerror = () => reject(new Error('语音流连接失败'))
    })

    // 必须等到服务端 ready 才算启动成功：本地模型缺失/加载失败时服务端会先发
    // error 再断开，若在这里当成成功，界面会显示「静待中」而不是错误原因。
    // Wait for the server's ready: a missing/failed local model makes the server send
    // error and close; treating that as success hides the real failure behind「静待中」.
    let readySettled = false
    let readyTimer: ReturnType<typeof setTimeout> | null = null
    let resolveReady!: () => void
    let rejectReady!: (e: Error) => void
    const ready = new Promise<void>((resolve, reject) => {
      resolveReady = resolve
      rejectReady = reject
    })
    const settleReady = (err?: Error) => {
      if (readySettled) return
      readySettled = true
      if (readyTimer) { clearTimeout(readyTimer); readyTimer = null }
      if (err) rejectReady(err)
      else resolveReady()
    }
    cancelStart = (e: Error) => settleReady(e)
    readyTimer = setTimeout(
      () => settleReady(new Error('本地引擎加载超时（20s），请检查模型与后端日志')),
      20_000,
    )

    const socket = ws
    socket.onmessage = (ev) => {
      let event: VoiceStreamEvent
      try {
        event = JSON.parse(ev.data) as VoiceStreamEvent
      } catch { return }
      opts.onEvent(event)
      if (event.type === 'ready') {
        settleReady()
      } else if (event.type === 'error') {
        // 服务端明确报错（模型缺失等）：不再自动重连，错误要透传给用户。
        // An explicit server error (missing model etc.): never retry; surface it.
        serverFailed = true
        const error = Object.assign(new Error(String(event.message || '语音服务错误')), {
          server: true,
          code: event.code,
        })
        opts.onError?.(error)
        settleReady(error)
      }
    }
    socket.onclose = () => {
      // 已被 stop()/新连接替换的旧 socket：其关闭事件与本句柄无关。
      // A stale socket replaced by stop()/a newer connection: its close is not ours.
      if (ws !== socket) return
      ws = null
      running = false
      // 就绪前断开 = 启动失败；就绪后的非主动断开 = 断线（自动重连）。
      // Close before ready = startup failure; an involuntary close after ready = a drop.
      settleReady(new Error('语音流在就绪前断开'))
      // 服务端关闭/报错时也要释放麦克风与音频图，否则麦克风会一直占着。
      // Release the mic and audio graph on a server close/error too; otherwise the mic stays held.
      releaseAudio()
      const willReconnect = readyOnce && !stopped && !serverFailed
      readyOnce = false
      if (willReconnect) scheduleReconnect(myGen)
      opts.onClose?.({ willReconnect })
    }
    socket.onerror = () => {
      const error = new Error('语音流连接错误')
      settleReady(error)
      opts.onError?.(error)
    }
    socket.send(JSON.stringify({
      type: 'start',
      sample_rate: ctx.sampleRate,
      channels: 1,
      format: 'pcm_s16le',
    }))
    // start 必须先到服务端；随后按序补发预 OPEN 帧（WS OPEN 后到 ready 前的帧由
    // 服务端排队，无需再门控）。start must arrive first; then flush the pre-open frames
    // in order (frames sent after OPEN but before ready are queued server-side).
    started = true
    // 闸门必须在预开帧之前到达服务端：否则首段会按默认 wake 处理（通话重连时误拦）。
    // The gate must reach the server before the pre-open frames; otherwise the first
    // segment is judged under the default wake gate (wrongly gated on call reconnect).
    sendGate()
    for (const frame of preopen.drain()) {
      try { socket.send(frame) } catch { /* 连接刚断，丢弃 */ }
    }
    preopenActive = false
    try {
      await ready
    } catch (e) {
      stop()
      throw e
    } finally {
      cancelStart = null
    }
    // 启动途中被 stop()/新启动覆盖：本次不得把 running 打开。
    // Stopped or superseded mid-start: this attempt must not mark the stream running.
    if (myGen !== gen || stopped) { stop(); return }
    readyOnce = true
    reconnectAttempt = 0
    running = true
  }

  /** 排一次指数退避重连；代际号变化或主动停止即放弃。
   *  Schedule one exponential-backoff retry; abandon it on a generation change or stop. */
  function scheduleReconnect(fromGen: number): void {
    if (reconnectTimer) return
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttempt, RECONNECT_MAX_MS)
    reconnectAttempt++
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (stopped || gen !== fromGen) return
      // 失败由下一次 onclose 再排一次（getUserMedia 失败则 stop() 终止重试）。
      // A failure schedules again via the next onclose (a mic failure stops retries).
      void start().catch(() => { /* 见下：下一轮 onclose 决定是否继续重试 */ })
    }, delay)
  }

  function releaseAudio(): void {
    preopen.clear()
    preopenActive = false
    started = false
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
    // 代际 +1 作废在飞的重连；stopped 让随后到达的 onclose 不再排新的重连。
    // Bump the generation to void in-flight retries; `stopped` keeps the later
    // onclose from scheduling a new one.
    gen++
    stopped = true
    readyOnce = false
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    cancelStart?.(new Error('语音流启动已取消'))
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
      if (value) preopen.clear()   // 静音期间缓存无意义 / buffered audio is useless while muted
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: value ? 'mute' : 'unmute' }))
      }
    },
    setGate(mode) {
      gate = mode
      sendGate()
    },
    isRunning: () => running,
  }
}
