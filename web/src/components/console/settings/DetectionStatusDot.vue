<template>
  <!-- 测试连接结果点：未测灰 / 测试中品牌色脉冲 / 成功绿 / 失败红。
       Connection-test status dot: idle grey / testing brand pulse / ok green / fail red.
       由调用方从 connResults / detecting 派生 status，组件本身不取数。 -->
  <span class="det-dot" :class="[`st-${status}`, { pulse: status === 'testing' }]" :title="title">
    <UiStatusDot :color="color" :size="8" :glow="status === 'ok' ? 6 : 0" />
  </span>
</template>

<script setup lang="ts">
/** 纯展示的测试连接状态点。Presentational connection-test status dot. */
import { computed } from 'vue'
import UiStatusDot from '../../ui/UiStatusDot.vue'

/** 检测状态。Detection status. */
export type DetectionStatus = 'idle' | 'testing' | 'ok' | 'fail'

const props = withDefaults(defineProps<{
  status: DetectionStatus
  detail?: string
}>(), { detail: '' })

/** 默认标题文案。Default title copy. */
const LABELS: Record<DetectionStatus, string> = {
  idle: '未测试',
  testing: '测试中…',
  ok: '连接成功',
  fail: '连接失败',
}
/** 圆点颜色。Dot colour. */
const COLORS: Record<DetectionStatus, string> = {
  idle: 'var(--text-3)',
  testing: 'var(--brand-c2)',
  ok: '#34d399',
  fail: '#f87171',
}
/** 显示颜色。Colour to render. */
const color = computed(() => COLORS[props.status])
/** 悬停标题（detail 优先）。Hover title (detail wins). */
const title = computed(() => props.detail || LABELS[props.status])
</script>

<style scoped>
.det-dot { display: inline-flex; align-items: center; }
.det-dot.pulse { animation: det-pulse 1.1s ease-in-out infinite; }
@keyframes det-pulse { 50% { opacity: .35; } }
</style>
