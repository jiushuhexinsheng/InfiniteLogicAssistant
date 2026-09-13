// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createSegmentRecorder } from '../useSegmentRecorder'

/** 分段录音：常驻 VAD 决定何时开始/结束一段，短于 minSpeechMs 的段直接丢弃（不上传）。
 *  Segment recording: an always-on VAD decides when a segment starts and ends; anything shorter
 *  than minSpeechMs is dropped outright and never uploaded. */

class FakeAnalyser {
  fftSize = 2048
  smoothingTimeConstant = 0.3
  /** 由测试驱动的 RMS 时间线（0..1）。Test-driven RMS timeline. */
  static timeline: number[] = []
  static cursor = 0
  getByteTimeDomainData(arr: Uint8Array) {
    // **必须推进 cursor**：不推进的话每次读到的都是 timeline[0]，「先说后静音」这类
    // 用例永远走不到静音，段永远不结束，测试会以错误的原因失败。
    // The cursor **must** advance: otherwise every read returns timeline[0], a "speech then
    // silence" case never reaches silence, the segment never ends, and the test fails for the
    // wrong reason.
    const i = Math.min(FakeAnalyser.cursor, FakeAnalyser.timeline.length - 1)
    FakeAnalyser.cursor++
    const rms = FakeAnalyser.timeline[i] ?? 0
    for (let k = 0; k < arr.length; k++) arr[k] = 128 + Math.round(rms * 127)
  }
}

class FakeRecorder {
  static instances: FakeRecorder[] = []
  state = 'inactive'
  ondataavailable: ((e: any) => void) | null = null
  onstop: (() => void) | null = null
  constructor(public stream: any, public opts: any) { FakeRecorder.instances.push(this) }
  static isTypeSupported() { return true }
  start() { this.state = 'recording' }
  stop() {
    this.state = 'inactive'
    // 产生一小段数据，让 onstop 能构造 Blob
    this.ondataavailable?.({ data: new Blob(['audio']) })
    this.onstop?.()
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeAnalyser.timeline = []; FakeAnalyser.cursor = 0
  FakeRecorder.instances = []
  ;(globalThis as any).AudioContext = function () {
    return {
      createMediaStreamSource: () => ({ connect: () => {} }),
      createAnalyser: () => new FakeAnalyser(),
      close: async () => {},
    }
  }
  ;(globalThis as any).MediaRecorder = FakeRecorder as any
})

afterEach(() => { vi.useRealTimers() })

const stream = { getTracks: () => [] } as any
const OPTS = { speechThreshold: 0.02, silenceMs: 1000, minSpeechMs: 300, maxMs: 10000 }

/** 语音→静音 会产生一段，并带上录音 Blob。Speech then silence emits a segment with a blob. */
it('检测到语音后静音 → 产出一段', async () => {
  const got: Blob[] = []
  FakeAnalyser.timeline = [0.5, 0.5, 0.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(2000)
  expect(got.length).toBe(1)
  rec.stop()
})

/** 只有静音时永远不产生段（VAD 是第一道成本闸：静音根本不上传）。 */
it('纯静音不产段', async () => {
  const got: Blob[] = []
  FakeAnalyser.timeline = [0]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(5000)
  expect(got.length).toBe(0)
  rec.stop()
})

/** 短于 minSpeechMs 的爆音被丢弃 —— 这是省调用量的关键，必须单独钉住。 */
it('短于 minSpeechMs 的爆音不产段', async () => {
  const got: Blob[] = []
  // 100ms 有声音，随后长期静音：短于 minSpeechMs=300ms
  FakeAnalyser.timeline = [0.5]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(100)     // 仅 ~1 个检查周期有声
  FakeAnalyser.timeline = [0]
  await vi.advanceTimersByTimeAsync(3000)
  expect(got.length).toBe(0)
  rec.stop()
})

/** stop() 后不再产段。No segments after stop(). */
it('stop 后不再产段', async () => {
  const got: Blob[] = []
  FakeAnalyser.timeline = [0.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  rec.stop()
  await vi.advanceTimersByTimeAsync(3000)
  expect(got.length).toBe(0)
})
