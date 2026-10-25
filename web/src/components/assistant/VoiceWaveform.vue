<template>
  <!-- 整段连续波形（不分割成柱）：最近约 1 秒的真实麦克风电平包络。
       One continuous waveform (no segmented bars): the recent real mic-level envelope. -->
  <svg
    class="voice-waveform"
    :class="{ active, dim: !active, muted: tone === 'muted' }"
    :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
    preserveAspectRatio="none"
    role="img"
    aria-hidden="true"
  >
    <defs>
      <linearGradient :id="gid" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#22d3ee" />
        <stop offset="0.22" stop-color="#818cf8" />
        <stop offset="0.45" stop-color="#e879f9" />
        <stop offset="0.68" stop-color="#fbbf24" />
        <stop offset="0.86" stop-color="#34d399" />
        <stop offset="1" stop-color="#22d3ee" />
      </linearGradient>
    </defs>
    <path :d="bandPath" :fill="`url(#${gid})`" />
  </svg>
</template>

<script setup lang="ts">
/** 连续语音波形（纯展示）。Continuous voice waveform (presentational). */
import { computed } from 'vue'
import { micHistory } from '../../composables/assistant/micLevel'

const props = withDefaults(defineProps<{
  active?: boolean
  bars?: number
  tone?: 'rgb' | 'muted'
}>(), {
  active: true,
  bars: 32,
  tone: 'rgb',
})

/** 每个实例独立的渐变 id（同页多实例不串色）。Per-instance gradient id. */
const gid = `vw-${Math.random().toString(36).slice(2, 8)}`

const WIDTH = 180
const HEIGHT = 34
const CENTER = HEIGHT / 2
const REST_AMP = 2
const MAX_AMP = 12

/** 采样电平（最近 n 个点）。Recent level samples. */
const samples = computed(() => micHistory.value.slice(-Math.max(2, props.bars)))

/** 每个采样点的半幅（静音也留一条细线）。Half-amplitude per sample. */
const amps = computed(() =>
  samples.value.map(level => REST_AMP + Math.min(1, Math.max(0, level)) * MAX_AMP))

/** 连续包络路径：上沿正序 + 下沿倒序，闭合为一条带状波形。 */
const bandPath = computed(() => {
  const n = amps.value.length
  const x = (i: number) => ((i / (n - 1)) * WIDTH).toFixed(2)
  const top = amps.value.map((a, i) => `${x(i)} ${(CENTER - a).toFixed(2)}`)
  const bottom = amps.value.map((a, i) => `${x(i)} ${(CENTER + a).toFixed(2)}`).reverse()
  return `M${top.join(' L')} L${bottom.join(' L')} Z`
})
</script>

<style scoped>
.voice-waveform {
  display: block; width: 180px; height: 34px; flex: none;
  transition: opacity var(--dur-base), filter var(--dur-base);
  filter: drop-shadow(0 0 5px rgba(103, 232, 249, .30));
}
.voice-waveform path { animation: vw-hue 12s linear infinite; transform-origin: center; }
@keyframes vw-hue { to { filter: hue-rotate(360deg); } }
.voice-waveform.active { opacity: .95; }
.voice-waveform.dim { opacity: .35; filter: none; }
.voice-waveform.dim path { animation-duration: 18s; }
.voice-waveform.muted { opacity: .35; filter: grayscale(1); }
.voice-waveform.muted path { animation: none; }
@media (prefers-reduced-motion: reduce) { .voice-waveform path { animation: none; } }
</style>
