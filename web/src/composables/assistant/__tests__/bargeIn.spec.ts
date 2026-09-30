// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { startBargeInMonitor, BARGE_IN_DURATION_MS } from '../bargeIn'

/**
 * barge-in 能量监控（docs/designs/02 批3）：
 * 连续超阈到时长触发一次、停后自停、失败静默降级为 no-op。
 *
 * Barge-in energy monitor (docs/designs/02 batch 3): fires once after sustained
 * above-threshold audio, stops itself after firing, and degrades silently to a
 * no-op on failure.
 */
describe('bargeIn 监控', () => {
  let stopTracks: ReturnType<typeof vi.fn>
  let loud: boolean

  beforeEach(() => {
    loud = true
    stopTracks = vi.fn()

    // 分析器桩：按 loud 标志填充字节域（200 → RMS≈0.56；128 → 静音）。
    // Analyser stub: fills the byte domain per the loud flag (200 → RMS≈0.56; 128 → silence).
    class FakeAnalyser {
      fftSize = 2048
      getByteTimeDomainData(buf: Uint8Array) { buf.fill(loud ? 200 : 128) }
    }
    class FakeCtx {
      createMediaStreamSource() { return { connect: () => { /* noop */ } } }
      createAnalyser() { return new FakeAnalyser() }
      close() { return Promise.resolve() }
    }
    ;(window as any).AudioContext = FakeCtx
    ;(navigator as any).mediaDevices = {
      getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTracks }] })),
    }
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  /** 持续超阈达到时长 → 触发一次且监控自停（流被关）。Sustained audio fires once
   *  and the monitor stops itself (stream released). */
  it('连续超阈到时长触发一次并自停', async () => {
    const onTrigger = vi.fn()
    const mon = startBargeInMonitor({ threshold: 0.04, durationMs: BARGE_IN_DURATION_MS, onTrigger })
    await vi.advanceTimersByTimeAsync(0)   // getUserMedia promise settle
    expect(onTrigger).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(BARGE_IN_DURATION_MS + 100)
    expect(onTrigger).toHaveBeenCalledTimes(1)
    expect(stopTracks).toHaveBeenCalled()
    // 再推进不再触发（已自停）。Advancing further does not fire again (self-stopped).
    await vi.advanceTimersByTimeAsync(2000)
    expect(onTrigger).toHaveBeenCalledTimes(1)
    mon.stop()                              // 幂等。Idempotent.
    mon.stop()
  })

  /** 中途静音则重计时不触发（防喇叭单个爆音误打断）。A dip below threshold resets
   *  the timer (a single speaker pop must not cut playback). */
  it('中途静音重置计时', async () => {
    const onTrigger = vi.fn()
    startBargeInMonitor({ threshold: 0.04, durationMs: BARGE_IN_DURATION_MS, onTrigger })
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(200)  // 超阈 200ms
    loud = false
    await vi.advanceTimersByTimeAsync(300)  // 静音 → 计时清零
    loud = true
    await vi.advanceTimersByTimeAsync(BARGE_IN_DURATION_MS - 100)  // 重新累计，差 100ms
    expect(onTrigger).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(200)
    expect(onTrigger).toHaveBeenCalledTimes(1)
  })

  /** 取流失败 → onFail 回调 + 句柄 no-op（调用方回退「播报期间停麦」旧行为）。
   *  Stream failure → onFail and a no-op handle (caller degrades to legacy mic-off). */
  it('取流失败静默降级', async () => {
    ;(navigator as any).mediaDevices.getUserMedia = vi.fn(async () => { throw new Error('denied') })
    const onTrigger = vi.fn()
    const onFail = vi.fn()
    const mon = startBargeInMonitor({ threshold: 0.04, durationMs: BARGE_IN_DURATION_MS, onTrigger, onFail })
    await vi.advanceTimersByTimeAsync(10)
    expect(onFail).toHaveBeenCalled()
    expect(onTrigger).not.toHaveBeenCalled()
    mon.stop()   // no-op 不抛。No-op without throwing.
  })
})
