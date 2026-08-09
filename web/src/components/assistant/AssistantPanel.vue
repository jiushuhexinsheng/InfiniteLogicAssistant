<template>
  <div
    class="float-panel"
    :class="visual.grad === 'rainbow' ? 'fx-rainbow' : ''"
    :style="panelStyle"
  >
    <!-- 顶栏：小逻头像 + 名称 + 只读状态 + 清空/关闭 -->
    <PanelHeader
      :visual="visual"
      :state="state"
      :wake-keyword="wakeKeyword"
      @clear="emit('clear')"
      @close="emit('close')"
    />

    <!-- 消息区 + 输入栏（由容器经默认 slot 填充） -->
    <div class="panel-body">
      <slot></slot>
    </div>

    <slot name="footer"></slot>
  </div>
</template>

<script setup lang="ts">
import PanelHeader from './PanelHeader.vue'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

defineProps<{
  state: AsstState
  visual: StateVisual
  panelStyle: Record<string, string>
  wakeKeyword: string
}>()

const emit = defineEmits<{ clear: []; close: [] }>()
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

.panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* 移动端 */
@media (max-width: 480px) {
  .float-panel {
    width: calc(100vw - 16px);
    right: 8px !important;
    max-height: 60vh;
  }
}
</style>
