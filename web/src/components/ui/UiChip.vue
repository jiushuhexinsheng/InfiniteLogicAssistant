<template>
  <span class="ui-chip" :class="`t-${tone}`">
    <UiStatusDot v-if="dot" :color="dotColor" :size="6" :glow="tone === 'ok' || tone === 'err' ? 6 : 0" />
    <span class="ui-chip-label"><slot /></span>
    <span v-if="detail" class="ui-chip-detail">{{ detail }}</span>
  </span>
</template>

<!-- 标签/徽章组件，可显示状态圆点和附加详情信息。Tag/badge component with optional status dot and detail text. -->
<script setup lang="ts">
import { computed } from 'vue'
import UiStatusDot from './UiStatusDot.vue'

/** 标签组件 Props：色调(状态)/是否显示状态圆点/附加详情文本。Chip props: tone (status), show status dot, extra detail text. */
const props = withDefaults(defineProps<{
  tone?: 'ok' | 'warn' | 'err' | 'info' | 'neutral'
  dot?: boolean
  detail?: string
}>(), { tone: 'neutral', dot: true })

const TONES: Record<string, string> = {
  ok: 'var(--ok)', warn: 'var(--warn)', err: 'var(--err)', info: 'var(--info)', neutral: 'var(--text-2)',
}
const dotColor = computed(() => TONES[props.tone])
</script>

<style scoped>
.ui-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-mono); font-size: var(--fs-2xs);
  padding: 3px 10px; border-radius: var(--r-full);
  border: 1px solid var(--border-soft); color: var(--text-2);
  background: var(--surface-control);
}
.ui-chip.t-ok { color: var(--ok); border-color: rgba(52, 211, 153, .35); background: rgba(52, 211, 153, .06); }
.ui-chip.t-warn { color: var(--warn); border-color: rgba(251, 191, 36, .35); background: rgba(251, 191, 36, .06); }
.ui-chip.t-err { color: var(--err); border-color: rgba(248, 113, 113, .35); background: rgba(248, 113, 113, .06); }
.ui-chip.t-info { color: var(--info); border-color: rgba(34, 211, 238, .35); background: rgba(34, 211, 238, .06); }
.ui-chip-detail { color: var(--text-3); font-size: 10px; }
</style>
