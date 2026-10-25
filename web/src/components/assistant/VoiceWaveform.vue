<template>
  <!-- 单一滚动波形：最近约 1 秒的真实麦克风电平历史。
       Single scrolling waveform driven by the recent real mic-level history. -->
  <div class="voice-waveform" :class="{ active, dim: !active }">
    <i v-for="(h, i) in bars" :key="i" class="vw-bar" :style="{ height: h + 'px' }"></i>
  </div>
</template>

<script setup lang="ts">
/** 语音波形（纯展示）。Voice waveform (presentational). */
import { computed } from 'vue'
import { micHistory } from '../../composables/assistant/micLevel'

const props = withDefaults(defineProps<{ active?: boolean; bars?: number }>(), {
  active: true,
  bars: 32,
})

/** 柱高（px），零值也保留 2px 基线。Bar heights in px with a 2px rest baseline. */
const bars = computed(() => {
  const history = micHistory.value.slice(-props.bars)
  return history.map(level => Math.round(2 + Math.min(1, Math.max(0, level)) * 18))
})
</script>

<style scoped>
.voice-waveform {
  display: flex; align-items: center; gap: 2px; height: 34px; flex: none;
  transition: opacity var(--dur-base);
}
.vw-bar {
  display: block; width: 2px; border-radius: 1px;
  background: linear-gradient(180deg, var(--brand-c2), var(--brand-c3));
  transition: height var(--dur-fast) linear;
}
.voice-waveform.active { opacity: .95; }
.voice-waveform.dim { opacity: .35; }
</style>
