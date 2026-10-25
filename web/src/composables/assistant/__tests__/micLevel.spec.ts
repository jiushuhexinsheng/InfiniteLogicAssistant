/**
 * 麦克风电平单例：EMA 平滑、声波条高度映射、归零，以及 HUD 滚动波形历史。
 * Mic-level singleton: EMA smoothing, sound-bar height mapping, zeroing, plus the HUD
 * waveform history.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  micLevel, reportMicLevel, resetMicLevel, eqBarHeights,
  micHistory, historySize, waveHeights,
} from '../micLevel'

describe('micLevel', () => {
  beforeEach(() => resetMicLevel())

  it('语音 RMS 快涨（rise α 大，一拍即可见起伏）', () => {
    reportMicLevel(0.25)            // 归一化到 1 → 0.6
    expect(micLevel.value).toBeGreaterThan(0.5)
  })

  it('静音帧慢落（fall α 小，平滑回落）', () => {
    reportMicLevel(0.25)
    const peak = micLevel.value
    reportMicLevel(0)
    expect(micLevel.value).toBeLessThan(peak)
    expect(micLevel.value).toBeGreaterThan(0)   // 单拍只落一截，不硬切
    for (let i = 0; i < 30; i++) reportMicLevel(0)
    expect(micLevel.value).toBeLessThan(0.01)
  })

  it('归一化封顶 1（超大振幅不越界）', () => {
    reportMicLevel(50)
    expect(micLevel.value).toBeLessThanOrEqual(1)
  })

  it('resetMicLevel 直接归零（停麦/播报门控）', () => {
    reportMicLevel(0.25)
    resetMicLevel()
    expect(micLevel.value).toBe(0)
  })

  it('声波条高度：静音 4px 基线，满电平错落有致且不超 14px', () => {
    expect(eqBarHeights(0)).toEqual([4, 4, 4, 4])
    const full = eqBarHeights(1)
    expect(full).toEqual([14, 10, 13, 9])
    expect(eqBarHeights(999).every(h => h <= 14)).toBe(true)   // 越界输入封顶
    expect(eqBarHeights(-1).every(h => h >= 4)).toBe(true)
  })

  it('每次上报推进波形历史，长度固定', () => {
    reportMicLevel(0.1)
    reportMicLevel(0.2)
    expect(micHistory.value).toHaveLength(historySize())
    expect(micHistory.value.at(-1)).toBeGreaterThan(0)
  })

  it('reset 把波形历史清空为基线', () => {
    reportMicLevel(0.2)
    resetMicLevel()
    expect(micHistory.value.every(v => v === 0)).toBe(true)
  })

  it('waveHeights 数量与高度范围正确', () => {
    reportMicLevel(0.25)
    const bars = waveHeights(16, 2, 18)
    expect(bars).toHaveLength(16)
    expect(Math.max(...bars)).toBeLessThanOrEqual(20)
    expect(Math.min(...bars)).toBeGreaterThanOrEqual(2)
  })
})
