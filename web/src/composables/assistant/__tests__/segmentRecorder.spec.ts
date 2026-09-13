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

/** stop() 时正在途中的那一段不上传：用户已经关掉唤醒了，不该还上传一段音频。
 *  A segment still in flight when stop() is called is never uploaded: the user just turned wake
 *  off, nothing should be sent. */
it('stop 时在途的段不上传', async () => {
  const got: Blob[] = []
  FakeAnalyser.timeline = [0.5]              // 一直有声：stop() 时正有一段在途
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(500)     // 已开录且 speechMs=500（远超 minSpeechMs）
  rec.stop()
  await vi.advanceTimersByTimeAsync(1000)
  expect(got.length).toBe(0)
})

/** 构造失败后必须复位记账状态：否则 speechSeen 卡在 true，后续语音再也切不出段（永久停摆）。
 *  A failed constructor must still reset the bookkeeping: otherwise speechSeen sticks at true and
 *  no later speech can ever start a segment again (a permanent stall). */
it('MediaRecorder 构造抛异常后，后续语音仍能切出段', async () => {
  const got: Blob[] = []
  const Real = FakeRecorder
  let made = 0
  // 第一台 recorder 构造即抛异常，之后恢复正常（模拟真实环境里偶发的构造失败）。
  // The first recorder throws from its constructor, later ones work (an occasional real failure).
  ;(globalThis as any).MediaRecorder = function (s: any, o: any) {
    if (made++ === 0) throw new Error('constructor failed')
    return new Real(s, o)
  }
  ;(globalThis as any).MediaRecorder.isTypeSupported = () => true

  // 第一个 tick 有声音（恰好撞上构造失败），随后静音：这一段不该产出。
  FakeAnalyser.timeline = [0.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(500)     // 语音：第一次 beginSegment 构造失败
  await vi.advanceTimersByTimeAsync(500)     // 静音：失败的段不应产出
  expect(got.length).toBe(0)
  FakeAnalyser.timeline = [0.5]
  await vi.advanceTimersByTimeAsync(500)     // 语音：必须还能开新段
  FakeAnalyser.timeline = [0]
  await vi.advanceTimersByTimeAsync(3000)    // 静音：这一段应当产出
  expect(got.length).toBe(1)
  rec.stop()
})

/** endSegment() 撞上「没有 live recorder」也必须复位：这台 recorder 起手就废（start 不进入
 *  recording、stop 也不触发 onstop），不会有 onstop 来收尾，只能就地复位。
 *  endSegment() meeting a recorder that never went live must reset in place too: this one is dead
 *  from the start (start() never enters recording, stop() never fires onstop), so no onstop will
 *  ever come to settle the segment. */
it('endSegment 撞上无 live recorder 后，后续语音仍能切出段', async () => {
  const got: Blob[] = []
  const Real = FakeRecorder
  let made = 0
  ;(globalThis as any).MediaRecorder = function (s: any, o: any) {
    const r = new Real(s, o)
    if (made++ === 0) {
      // 模拟一台已自行失效的录音器：既不进入 recording，也不会回调 onstop。
      r.start = () => { r.state = 'inactive' }
      r.stop = () => { r.state = 'inactive' }
    }
    return r
  }
  ;(globalThis as any).MediaRecorder.isTypeSupported = () => true

  FakeAnalyser.timeline = [0.5]
  const rec = createSegmentRecorder(stream, { ...OPTS, onSegment: (b) => got.push(b) })
  rec.start()
  await vi.advanceTimersByTimeAsync(500)     // 语音：第一台（哑的）recorder
  FakeAnalyser.timeline = [0]
  await vi.advanceTimersByTimeAsync(3000)    // 静音：endSegment 撞上无 live recorder
  FakeAnalyser.timeline = [0.5]
  await vi.advanceTimersByTimeAsync(500)     // 语音：必须还能开新段（第二台正常）
  FakeAnalyser.timeline = [0]
  await vi.advanceTimersByTimeAsync(3000)    // 静音：这一段应当产出
  expect(got.length).toBe(1)
  rec.stop()
})
