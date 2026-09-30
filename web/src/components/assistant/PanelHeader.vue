<template>
  <!-- 面板顶部栏：头像 + 名称 + 状态指示器 + 操作按钮。Panel header: avatar + name + status indicator + action buttons. -->
  <div class="panel-header">
    <!-- 助手头像。Assistant avatar. -->
    <span class="ph-avatar"><UiIcon name="brain" :size="16" /></span>
    <span class="ph-name">衍衡</span>
    <!-- 停止朗读：播报期间才出现（打断白名单的 UI 入口，docs/designs/02 §3.1）。
         Stop reading: only visible during playback (the UI entry of the interrupt
         whitelist, docs/designs/02 §3.1). -->
    <UiIconButton
      v-if="speaking"
      title="停止朗读"
      @click="stopSpeak('ui')"
    ><UiIcon name="stop" :size="13" /></UiIconButton>
    <!-- 清空对话按钮。Clear conversation button. -->
    <UiIconButton title="清空对话" @click="emit('clear')"><UiIcon name="trash" :size="14" /></UiIconButton>
    <!-- 关闭面板按钮。Close panel button. -->
    <UiIconButton title="关闭" @click="emit('close')"><UiIcon name="close" :size="14" /></UiIconButton>
  </div>
</template>

<script setup lang="ts">
import { UiIconButton, UiIcon } from '../ui'
import { speaking, stopSpeak } from '../../composables/assistant/useTts'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

/**
 * 组件属性定义。Component props definition.
 * @property visual - 状态对应的视觉配置。Visual configuration for the current state.
 * @property state - 助手当前状态。Current assistant state.
 * @property wakeHint - 唤醒词提示文案。Wake keyword hint.
 */
defineProps<{
  visual: StateVisual
  state: AsstState
  wakeHint: string
}>()

/**
 * 组件事件定义。Component events definition.
 * @event clear - 清空对话历史。Clear conversation history.
 * @event close - 关闭面板。Close the panel.
 */
const emit = defineEmits<{ clear: []; close: [] }>()
</script>

<style scoped>
/* 面板头部栏。Panel header bar. */
.panel-header {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 11px 14px;
  background: rgba(15, 23, 42, .9);
  border-bottom: 1px solid var(--border-soft);
}
/* 助手头像。Assistant avatar. */
.ph-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--brand-grad);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0f172a;
  flex-shrink: 0;
}
/* 助手名称。Assistant name. */
.ph-name { font-size: 14px; font-weight: 600; color: var(--text-1); white-space: nowrap; flex: 1; }
</style>
