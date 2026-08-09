<template>
  <div
    class="float-trigger"
    :class="[visual.fx, visual.grad === 'rainbow' ? 'fx-rainbow' : '', { active: expanded }]"
    :style="[triggerStyle, { '--fx-color': visual.color }]"
    @pointerdown="onDragStart"
    @touchstart.prevent="onTouchStart"
    @touchmove.prevent="onTouchMove"
    @touchend="onTouchEnd"
    @click="onClick"
    @dblclick="emit('dblclick')"
  >
    <Icon :name="visual.icon" :size="24" class="trigger-icon" style="color:#fff" />
    <span v-if="!expanded && messageDot" class="new-dot"></span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import Icon from '../Icon.vue'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  pos: { x: number; y: number }
  state: AsstState
  visual: StateVisual
  messageDot: boolean
  expanded: boolean
}>()

const emit = defineEmits<{
  'update:pos': [pos: { x: number; y: number }]
  click: []
  dblclick: []
}>()

const dragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })
const clickTime = ref(0)

function onDragStart(e: PointerEvent) {
  dragOffset.value = { x: e.clientX - props.pos.x, y: e.clientY - props.pos.y }
  clickTime.value = Date.now()
  const target = e.target as HTMLElement
  target.setPointerCapture?.(e.pointerId)
  document.addEventListener('pointermove', onDragMove)
  document.addEventListener('pointerup', onDragEnd)
}

function onDragMove(e: PointerEvent) {
  if (Math.abs(e.clientX - dragOffset.value.x - props.pos.x) > 3 ||
      Math.abs(e.clientY - dragOffset.value.y - props.pos.y) > 3) dragging.value = true
  emit('update:pos', {
    x: Math.max(0, Math.min(window.innerWidth - 56, e.clientX - dragOffset.value.x)),
    y: Math.max(0, Math.min(window.innerHeight - 56, e.clientY - dragOffset.value.y)),
  })
}

function onDragEnd(e: PointerEvent) {
  (e.target as HTMLElement).releasePointerCapture?.(e.pointerId)
  document.removeEventListener('pointermove', onDragMove)
  document.removeEventListener('pointerup', onDragEnd)
}

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 1) {
    const t = e.touches[0]
    dragOffset.value = { x: t.clientX - props.pos.x, y: t.clientY - props.pos.y }
    clickTime.value = Date.now()
  }
}

function onTouchMove(e: TouchEvent) {
  if (e.touches.length === 1) {
    const t = e.touches[0]
    if (Math.abs(t.clientX - dragOffset.value.x - props.pos.x) > 3 ||
        Math.abs(t.clientY - dragOffset.value.y - props.pos.y) > 3) dragging.value = true
    emit('update:pos', {
      x: Math.max(0, Math.min(window.innerWidth - 56, t.clientX - dragOffset.value.x)),
      y: Math.max(0, Math.min(window.innerHeight - 56, t.clientY - dragOffset.value.y)),
    })
  }
}

function onTouchEnd() { /* 单击由 click 事件处理 */ }

function onClick() {
  if (dragging.value) { dragging.value = false; return }
  if (Date.now() - clickTime.value < 300) emit('click')
}

onUnmounted(() => {
  document.removeEventListener('pointermove', onDragMove)
  document.removeEventListener('pointerup', onDragEnd)
})

const triggerStyle = computed(() => ({
  right: (window.innerWidth - props.pos.x - 56) + 'px',
  bottom: (window.innerHeight - props.pos.y - 56) + 'px',
}))
</script>

<style scoped>
.float-trigger {
  position: fixed;
  z-index: 9999;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #1e293b;
  /* 品牌渐变描边 + 慢呼吸光晕 */
  border: 1px solid transparent;
  background:
    linear-gradient(#1e293b, #1e293b) padding-box,
    var(--brand-grad) border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  user-select: none;
  touch-action: none;
  transition: transform 0.2s, box-shadow 0.3s;
  animation: ball-breathe 3s ease-in-out infinite;
}
.float-trigger:hover { transform: scale(1.08); }
.float-trigger.active { transform: scale(0.95); }
@keyframes ball-breathe {
  0%, 100% { box-shadow: 0 0 8px rgba(165, 180, 252, .25); }
  50%      { box-shadow: 0 0 18px rgba(110, 231, 183, .4), 0 0 30px rgba(103, 232, 249, .2); }
}
.trigger-icon { font-size: 24px; line-height: 1; }
.new-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ef4444;
  animation: blink 1s infinite;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* ── 状态特效（accent 色来自 STATE_VISUALS.color，经 --fx-color 注入）── */
.float-trigger::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid transparent;
  pointer-events: none;
}
.float-trigger.fx-listening::after {
  border-color: var(--fx-color, #22c55e);
  animation: fx-radar 1.6s ease-out infinite;
}
.float-trigger.fx-recording::after {
  border-color: var(--fx-color, #ef4444);
  animation: fx-radar 1.1s ease-out infinite;
}
.float-trigger.fx-recording {
  animation: fx-shake 0.25s linear infinite;
}
.float-trigger.fx-transcribing::after {
  border-top-color: var(--fx-color, #a855f7);
  animation: fx-spin 1.1s linear infinite;
}
.float-trigger.fx-thinking::after {
  border-top-color: var(--fx-color, #f97316);
  animation: fx-spin 0.8s linear infinite;
}
.float-trigger.fx-tool_calling::after {
  border-top-color: var(--fx-color, #06b6d4);
  animation: fx-spin 0.6s linear infinite;
}
.float-trigger.fx-responding::after {
  border-color: var(--fx-color, #3b82f6);
  animation: fx-radar 1.3s ease-out infinite;
}
.float-trigger.fx-done {
  animation: fx-done-flash 0.6s ease-out;
}
.float-trigger.fx-error::after {
  border-color: var(--fx-color, #ef4444);
}
.float-trigger.fx-error {
  animation: fx-shake 0.3s linear infinite;
}
@keyframes fx-radar {
  0% { transform: scale(.75); opacity: .9; }
  100% { transform: scale(1.9); opacity: 0; }
}
@keyframes fx-spin { to { transform: rotate(360deg); } }
@keyframes fx-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-2px); }
  75% { transform: translateX(2px); }
}
@keyframes fx-done-flash {
  0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, .6); }
  100% { box-shadow: 0 0 0 22px rgba(34, 197, 94, 0); }
}

/* ── 彩虹激活（listening / recording）── */
.float-trigger.fx-rainbow {
  border-color: transparent;
  background:
    linear-gradient(#1e293b, #1e293b) padding-box,
    var(--rainbow) border-box;
  animation: ball-breathe 1.2s ease-in-out infinite, rainbow-hue 3s linear infinite;
}
.float-trigger.fx-rainbow::after {
  border-color: rgba(255, 255, 255, .35);
  animation: fx-radar 1.2s ease-out infinite;
}
</style>
