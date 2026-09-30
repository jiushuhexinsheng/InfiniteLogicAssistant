/**
 * barge-in 监控 —— 播报期间的「用户开口即打断」能量检测（docs/designs/02 批3）。
 *
 * 与段录音器（useSegmentRecorder）分离的独立监听流：开启一个带回声消除的
 * getUserMedia 流 + AnalyserNode 轮询 RMS，连续超阈达到时长即触发一次 onTrigger
 * （由调用方接 stopSpeak('barge_in')）。任何取流/上下文失败都静默降级 —— 返回
 * no-op stop，调用方维持「播报期间停麦」的旧行为，打断功能不可用不致坏。
 *
 * 触发后监控立即自停；剩余余响由既有回声护栏（ECHO_GUARD_MS=1200，speaking→false
 * 时武装）拦截，无需本模块再设第二道丢弃窗。
 *
 * Barge-in monitor — "user speech cuts playback" energy detection during playback
 * (docs/designs/02 batch 3). A listening stream separate from the segment recorder:
 * an echo-cancelled getUserMedia stream plus AnalyserNode RMS polling fires
 * onTrigger once after the level stays above threshold for the required duration
 * (the caller wires it to stopSpeak('barge_in')). Any stream/context failure
 * degrades silently to a no-op stop, so the caller keeps the legacy
 * "mic off while speaking" behaviour — the feature being unavailable never breaks
 * playback. The monitor stops itself after firing; the remaining echo is handled
 * by the existing echo guard (ECHO_GUARD_MS=1200, armed on speaking→false), so no
 * second discard window is needed here.
 */

/** 监控句柄：stop 幂等，可安全重复调用。Monitor handle: idempotent stop. */
export interface BargeInMonitor {
  stop: () => void
}

/** 监控参数。Monitor options. */
export interface BargeInOptions {
  /** RMS 阈值（0-1，调用方按 silence_threshold × 2 下发）。RMS threshold (caller sends silence_threshold × 2). */
  threshold: number
  /** 连续超阈时长（毫秒）。Sustained-above-threshold duration (ms). */
  durationMs: number
  /** 命中回调（只触发一次）。Fired once. */
  onTrigger: () => void
  /** 取流/上下文失败回调（可选，仅记日志用）。Failure callback (optional, logging only). */
  onFail?: (err: unknown) => void
}

/** 轮询间隔（毫秒）。Polling interval (ms). */
const TICK_MS = 100

/** 判定用户开口所需的连续超阈时长（毫秒）。Sustained duration that counts as user speech. */
export const BARGE_IN_DURATION_MS = 400

/**
 * 启动 barge-in 监控。Start the barge-in monitor.
 *
 * @param opts 监控参数。Monitor options.
 * @returns 监控句柄（失败时为 no-op）。Monitor handle (no-op on failure).
 */
export function startBargeInMonitor(opts: BargeInOptions): BargeInMonitor {
  let stopped = false
  let stream: MediaStream | null = null
  let ctx: AudioContext | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  let aboveSince: number | null = null
  let fired = false

  const stop = () => {
    if (stopped) return
    stopped = true
    if (timer) { clearInterval(timer); timer = null }
    aboveSince = null
    try { stream?.getTracks().forEach(t => t.stop()) } catch { /* ignore */ }
    stream = null
    try { void ctx?.close() } catch { /* ignore */ }
    ctx = null
  }

  try {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      throw new Error('getUserMedia unavailable')
    }
    void navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    }).then((s) => {
      if (stopped) { s.getTracks().forEach(t => t.stop()); return }
      stream = s
      const AC = (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext }).AudioContext
        || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AC) throw new Error('AudioContext unavailable')
      ctx = new AC()
      const src = ctx.createMediaStreamSource(s)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 2048
      src.connect(analyser)
      const buf = new Uint8Array(analyser.fftSize)
      timer = setInterval(() => {
        if (stopped) return
        analyser.getByteTimeDomainData(buf)
        // RMS（与 useSegmentRecorder 同口径：字节域 128 为 0）。
        // RMS (same convention as useSegmentRecorder: byte domain, 128 = silence).
        let sum = 0
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128
          sum += v * v
        }
        const rms = Math.sqrt(sum / buf.length)
        const now = Date.now()
        if (rms > opts.threshold) {
          if (aboveSince === null) aboveSince = now
          if (!fired && now - aboveSince >= opts.durationMs) {
            fired = true
            stop()
            opts.onTrigger()
          }
        } else {
          aboveSince = null
        }
      }, TICK_MS)
    }).catch((err) => {
      opts.onFail?.(err)
      stop()
    })
  } catch (err) {
    opts.onFail?.(err)
    stop()
  }
  return { stop }
}
