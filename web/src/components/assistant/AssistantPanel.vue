<template>
  <!-- 助手浮窗面板主容器。Main container for the assistant floating panel. -->
  <div
    class="float-panel"
    :class="visual.grad === 'rainbow' ? 'fx-rainbow' : ''"
    :style="panelStyle"
  >
    <!-- 顶栏：小逻头像 + 名称 + 只读状态 + 清空/关闭。Top bar: avatar + name + status + clear/close buttons. -->
    <PanelHeader
      :visual="visual"
      :state="state"
      :wake-keyword="wakeKeyword"
      @clear="emit('clear')"
      @close="emit('close')"
    />

    <!-- 消息区 + 输入栏（由容器经默认 slot 填充）。Message area + input bar (filled via default slot by parent). -->
    <div class="panel-body">
      <slot></slot>
    </div>

    <!-- 底部插槽，用于放置额外操作区。Footer slot for additional action areas. -->
    <slot name="footer"></slot>
  </div>
</template>

<script setup lang="ts">
import PanelHeader from './PanelHeader.vue'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

/**
 * 组件属性定义。Component props definition.
 * @property state - 助手当前状态。Current assistant state.
 * @property visual - 状态对应的视觉配置。Visual configuration for the current state.
 * @property panelStyle - 面板的动态内联样式。Dynamic inline style for the panel.
 * @property wakeKeyword - 语音唤醒关键词。Voice wake keyword.
 */
defineProps<{
  state: AsstState
  visual: StateVisual
  panelStyle: Record<string, string>
  wakeKeyword: string
}>()

/**
 * 组件事件定义。Component events definition.
 * @event clear - 清空对话历史。Clear conversation history.
 * @event close - 关闭面板。Close the panel.
 */
const emit = defineEmits<{ clear: []; close: [] }>()
</script>

<style scoped>
/* 浮窗面板主体样式。Main floating panel styles. */
.float-panel {
  position: fixed;
  z-index: 9998;
  width: 368px;
  max-height: 528px;
  /* 品牌渐变细边框（background-clip 双层技巧，支持圆角）+ 玻璃质感 + 深空晕染背景。
     Brand gradient border (background-clip double-layer trick, supports border-radius) + glass effect + deep-space glow background. */
  border: 1px solid transparent;
  background:
    radial-gradient(120% 60% at 50% 0%, rgba(103, 232, 249, .08), transparent 60%),
    linear-gradient(var(--glass-bg-strong), var(--glass-bg-strong)) padding-box,
    var(--brand-grad) border-box;
  backdrop-filter: blur(18px) saturate(140%);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  border-radius: var(--r-2xl);
  box-shadow: var(--shadow-3), 0 0 0 1px rgba(139, 157, 255, .04);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
/* 聆听/录音：边框切彩虹。Listening/recording: rainbow border effect. */
.float-panel.fx-rainbow {
  background:
    radial-gradient(120% 60% at 50% 0%, rgba(103, 232, 249, .08), transparent 60%),
    linear-gradient(var(--panel-bg), var(--panel-bg)) padding-box,
    var(--rainbow) border-box;
  animation: rainbow-hue 4s linear infinite;
}

/* 面板内容区。Panel body content area. */
.panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 2px;
}

/* 移动端适配。Mobile responsive adaptation. */
@media (max-width: 480px) {
  .float-panel {
    width: calc(100vw - 16px);
    right: 8px !important;
    max-height: 60vh;
  }
}
</style>
