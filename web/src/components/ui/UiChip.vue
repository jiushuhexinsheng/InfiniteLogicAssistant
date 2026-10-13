<template>
  <span class="ui-chip" :class="`t-${tone}`">
    <!-- 圆点光晕：原先只给 ok/err，其余 tone 是哑的 —— 同一排 chip 里有的「亮」有的不亮，
         读起来像状态不同而不是配色不同。现在整族带光（neutral 除外，它没有语义色）。
         Dot glow: used to cover only ok/err, leaving the other tones dull — in one row that read
         as "different states" rather than "different tones". Now the whole family glows
         (except neutral, which has no semantic colour). -->
    <UiStatusDot v-if="dot" :color="dotColor" :size="6" :glow="tone === 'neutral' ? 0 : 6" />
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
  display: inline-flex; align-items: center; gap: var(--sp-q6);
  font-family: var(--font-mono); font-size: var(--fs-2xs);
  padding: var(--sp-q3) var(--sp-q10); border-radius: var(--r-full);
  border: 1px solid var(--border-soft); color: var(--text-2);
  background: var(--surface-control);
}
/* 语义色的 chip 自发光（科技感）：色环 + 小半径外光。
   ⚠️ 半径**刻意压小**（7px / -2px spread）：实测大模糊的阴影加在带渐变/复合层的元素上会让
   headless 截图间歇性差像素（见 git log 028596a）。小半径是这套截取里被证明稳的量级。
   Self-lit semantic chips: a colour ring plus a small-radius bloom. The radius is deliberately
   kept small — a large blurred shadow made the headless capture intermittently unstable
   (see commit 028596a); a small radius is the magnitude proven stable here. */
.ui-chip.t-ok { color: var(--ok); border-color: rgba(52, 211, 153, .35); background: rgba(52, 211, 153, .06);
  box-shadow: 0 0 7px -2px rgba(52, 211, 153, .5); }
.ui-chip.t-warn { color: var(--warn); border-color: rgba(251, 191, 36, .35); background: rgba(251, 191, 36, .06);
  box-shadow: 0 0 7px -2px rgba(251, 191, 36, .5); }
.ui-chip.t-err { color: var(--err); border-color: rgba(248, 113, 113, .35); background: rgba(248, 113, 113, .06);
  box-shadow: 0 0 7px -2px rgba(248, 113, 113, .5); }
.ui-chip.t-info { color: var(--info); border-color: rgba(34, 211, 238, .35); background: rgba(34, 211, 238, .06);
  box-shadow: 0 0 7px -2px rgba(34, 211, 238, .5); }
.ui-chip-detail { color: var(--text-3); font-size: var(--fs-3xs); }
</style>
