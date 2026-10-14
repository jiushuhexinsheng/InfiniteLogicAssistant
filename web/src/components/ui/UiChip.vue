<template>
  <span class="ui-chip" :class="`t-${tone}`" :style="solidStyle">
    <!-- 圆点光晕：原先只给 ok/err，其余 tone 是哑的 —— 同一排 chip 里有的「亮」有的不亮，
         读起来像状态不同而不是配色不同。现在整族带光（neutral 除外，它没有语义色）。
         Dot glow: used to cover only ok/err, leaving the other tones dull — in one row that read
         as "different states" rather than "different tones". Now the whole family glows
         (except neutral, which has no semantic colour). -->
    <UiStatusDot v-if="showDot" :color="dotColor" :size="6" :glow="tone === 'neutral' ? 0 : 6" />
    <span class="ui-chip-label"><slot /></span>
    <span v-if="detail" class="ui-chip-detail">{{ detail }}</span>
  </span>
</template>

<!-- 标签/徽章组件，可显示状态圆点和附加详情信息。Tag/badge component with optional status dot and detail text. -->
<script setup lang="ts">
import { computed } from 'vue'
import UiStatusDot from './UiStatusDot.vue'

/** 标签组件 Props：色调(状态)/是否显示状态圆点/附加详情文本/实心态的动态填充色。
 *  Chip props: tone (status), show status dot, extra detail text, and the solid tone's dynamic fill. */
const props = withDefaults(defineProps<{
  tone?: 'ok' | 'warn' | 'err' | 'info' | 'neutral' | 'solid'
  dot?: boolean
  detail?: string
  /** `tone="solid"` 的填充色（动态，通常来自助手状态色）。没有它 solid 就退回基类的底。
   *  Fill colour for `tone="solid"` (dynamic, usually the assistant state colour); without it
   *  solid falls back to the base chip's surface. */
  color?: string
}>(), { tone: 'neutral', dot: true, color: '' })

const TONES: Record<string, string> = {
  ok: 'var(--ok)', warn: 'var(--warn)', err: 'var(--err)', info: 'var(--info)', neutral: 'var(--text-2)',
}
/** solid 是「整块填充就是状态」的形态，圆点在里面没有意义（它与底色同义）—— 故强制不显，
 *  不靠调用方记得传 `:dot="false"`。
 *  solid is the "the fill itself is the status" form, where a dot is meaningless (it would restate
 *  the fill) — so it is suppressed here rather than relying on callers to remember `:dot="false"`. */
const showDot = computed(() => props.dot && props.tone !== 'solid')
const dotColor = computed(() => TONES[props.tone])
const solidStyle = computed(() => (props.tone === 'solid' && props.color ? { background: props.color } : undefined))
</script>

<style scoped>
.ui-chip {
  display: inline-flex; align-items: center; gap: var(--sp-q6);
  font-family: var(--font-mono); font-size: var(--fs-2xs);
  padding: var(--sp-1) var(--sp-q10); border-radius: var(--r-full);
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
/* 实心态（`tone="solid"`）：整块填充 = 动态状态色（`color` prop，走内联 style），文字用
   on-brand 的深墨。逐像素复刻起始页原先的 `.status-badge`（无边框 / sans 12px / 4px 12px 内边距）
   —— 收编的目标是「站内徽章只剩一份实现」，不是改观感。
   ⚠️ 下面这些覆盖是**有意**的：solid 与基类 chip 共享的只有圆角与 display。要给它加边框、
   换字体或改内边距，先想清楚这会同时改掉起始页那个徽章。
   Solid form (`tone="solid"`): the whole pill is filled with the dynamic state colour (the `color`
   prop, applied inline) and the text uses the on-brand dark ink. Reproduces the start page's former
   `.status-badge` pixel for pixel (no border / sans 12px / 4px 12px padding) — the goal is one badge
   implementation, not a new look. The overrides below are deliberate: solid shares only the radius
   and display with the base chip. */
.ui-chip.t-solid {
  border: none;
  font-family: var(--font-sans);
  font-size: var(--fs-xs);
  font-weight: 500;
  padding: var(--sp-1) var(--sp-3);
  color: var(--text-on-brand);
}
</style>
