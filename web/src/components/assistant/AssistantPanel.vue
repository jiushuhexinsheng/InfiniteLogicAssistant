<template>
  <div
    class="float-panel"
    :class="visual.grad === 'rainbow' ? 'fx-rainbow' : ''"
    :style="panelStyle"
  >
    <!-- 拖拽手柄 -->
    <div class="panel-handle">
      <span class="handle-dots">⋮⋮</span>
      <span class="handle-title">小逻</span>
      <button class="handle-close" @click="emit('close')">✕</button>
    </div>

    <slot></slot>

    <slot name="footer"></slot>
  </div>
</template>

<script setup lang="ts">
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

defineProps<{
  state: AsstState
  visual: StateVisual
  panelStyle: Record<string, string>
}>()

const emit = defineEmits<{ close: [] }>()
</script>

<style scoped>
.float-panel {
  position: fixed;
  z-index: 9998;
  width: 360px;
  max-height: 520px;
  /* 品牌渐变细边框（background-clip 双层技巧，支持圆角）+ 深空晕染背景 */
  border: 1px solid transparent;
  background:
    radial-gradient(120% 60% at 50% 0%, rgba(103, 232, 249, .08), transparent 60%),
    linear-gradient(var(--panel-bg), var(--panel-bg)) padding-box,
    var(--brand-grad) border-box;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, .4);
}
/* 聆听/录音：边框切彩虹 */
.float-panel.fx-rainbow {
  background:
    radial-gradient(120% 60% at 50% 0%, rgba(103, 232, 249, .08), transparent 60%),
    linear-gradient(var(--panel-bg), var(--panel-bg)) padding-box,
    var(--rainbow) border-box;
  animation: rainbow-hue 4s linear infinite;
}

.panel-handle {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  cursor: grab;
  background: #0f172a;
  border-bottom: 1px solid var(--border-base);
  gap: 8px;
}
.panel-handle:active { cursor: grabbing; }
.handle-dots { color: var(--text-3); font-size: 16px; letter-spacing: 2px; }
.handle-title { flex: 1; color: var(--text-1); font-size: 14px; font-weight: 600; }
.handle-close {
  background: none; border: none; color: var(--text-2); cursor: pointer;
  font-size: 16px; padding: 2px 6px; border-radius: 4px;
}
.handle-close:hover { background: #334155; color: var(--text-1); }

/* 移动端 */
@media (max-width: 480px) {
  .float-panel {
    width: calc(100vw - 16px);
    right: 8px !important;
    max-height: 60vh;
  }
}
</style>
