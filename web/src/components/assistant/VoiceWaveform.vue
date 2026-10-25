<template>
  <!-- 整段连续波形（不分割成柱）：最近约 1 秒的真实麦克风电平包络。
       One continuous waveform (no segmented bars): the recent real mic-level envelope. -->
  <svg
    class="voice-waveform"
    :class="{ active, dim: !active }"
    :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
    preserveAspectRatio="none"
    role="img"
    aria-hidden="true"
  >
    <path :d="bandPath" fill="currentColor" />
  </svg>
</template>

<script setup lang="ts">
/** 连续语音波形（纯展示）。Continuous voice waveform (presentational). */
import { computed } from 'vue'
import { micHistory } from '../../composables/assistant/micLevel'

const props = withDefaults(defineProps<{ active?: boolean; bars?: number }>(), {
  active: true,
  bars: 32,
})

const WIDTH = 80
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
  display: block; width: 80px; height: 34px; flex: none;
  color: var(--brand-c2);
  transition: opacity var(--dur-base), color var(--dur-base);
  filter: drop-shadow(0 0 4px rgba(103, 232, 249, .28));
}
.voice-waveform.active { opacity: .95; }
.voice-waveform.dim { opacity: .35; filter: none; }
</style>
