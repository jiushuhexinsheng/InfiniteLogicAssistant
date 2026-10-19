import { ref } from 'vue'

/**
 * 麦克风电平单例：供状态胶囊/迷你条的声波条随真实音量起伏。
 *
 * 数据源是 AudioWorklet 每帧上报的 RMS（streamClient 的 onLevel 回调）——
 * 不另开采集，麦克风关闭/播报静音时由调用方归零。
 * 电平保持 0（声波条静止，可接受降级）。
 *
 * Mic-level singleton driving the sound bars in the status pill / mini player with
 * real volume. Fed by the segment recorder's existing 100ms RMS tick (its onLevel
 * callback) — no second capture path; the caller zeroes it when the mic stops
 * (playback gate / wake off). Webspeech mode has no segment recorder, so the level
 * stays 0 (bars rest — an acceptable degradation).
 */
export const micLevel = ref(0)

/** 声波条 4 根的高度权重（错落感）。Per-bar height weights for the sound bars. */
export const EQ_MULTIPLIERS = [1, 0.6, 0.85, 0.5] as const

/**
 * 由电平算 4 根 bar 的像素高度（min..min+span）。
 * Compute the four bar heights (px) from the level (min..min+span).
 */
export function eqBarHeights(level: number, min = 4, span = 10): number[] {
  const l = Math.min(1, Math.max(0, level))
  return EQ_MULTIPLIERS.map(m => Math.round(min + l * span * m))
}

/** 语音实用 RMS 幅度的归一化除数（0.25 ≈ 正常说话上限，超出截到 1）。 */
const RMS_DIVISOR = 0.25
/** 快涨慢落的 EMA 系数：上涨灵敏、下落平滑。Rise/fall EMA coefficients. */
const RISE_ALPHA = 0.6
const FALL_ALPHA = 0.25

/** 段录音器每 tick 上报原始 RMS → EMA 平滑写入 micLevel。
 *  Segment recorder reports the raw RMS each tick → EMA-smoothed into micLevel. */
export function reportMicLevel(rms: number): void {
  const target = Math.min(1, Math.max(0, rms / RMS_DIVISOR))
  const alpha = target > micLevel.value ? RISE_ALPHA : FALL_ALPHA
  micLevel.value = micLevel.value + (target - micLevel.value) * alpha
}

/** 麦克风停止/段录音器收尾时归零（声波条回落基线）。Zero on mic stop. */
export function resetMicLevel(): void {
  micLevel.value = 0
}
