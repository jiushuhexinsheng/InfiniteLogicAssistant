/**
 * AudioWorklet 定长分帧：把麦克风浮点采样攒成 20 ms 帧，转 PCM16 交给主线程。
 *
 * AudioWorklet fixed-size framing: accumulate mic float samples into 20 ms frames and
 * hand PCM16 to the main thread.
 *
 * 主线程负责 WebSocket；worklet 只做「攒帧 + RMS」，避免在主线程做采样级计算。
 * The main thread owns the WebSocket; the worklet only frames and computes RMS, keeping
 * sample-level work off the main thread.
 */
class FrameProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super()
    const opts = (options && options.processorOptions) || {}
    this.frameSize = opts.frameSize || 320
    this.buf = new Float32Array(this.frameSize)
    this.offset = 0
    this.sum = 0
    this.count = 0
  }

  process(inputs) {
    const input = inputs[0]
    const ch = input && input[0]
    if (!ch || !ch.length) return true

    for (let i = 0; i < ch.length; i++) {
      const v = ch[i]
      this.buf[this.offset++] = v
      this.sum += v * v
      this.count++
      if (this.offset >= this.frameSize) {
        const pcm = new Int16Array(this.frameSize)
        for (let j = 0; j < this.frameSize; j++) {
          const s = Math.max(-1, Math.min(1, this.buf[j]))
          pcm[j] = s < 0 ? s * 32768 : s * 32767
        }
        const rms = Math.sqrt(this.sum / Math.max(1, this.count))
        this.port.postMessage({ pcm: pcm.buffer, rms }, [pcm.buffer])
        this.offset = 0
        this.sum = 0
        this.count = 0
      }
    }
    return true
  }
}

registerProcessor('frame-processor', FrameProcessor)
