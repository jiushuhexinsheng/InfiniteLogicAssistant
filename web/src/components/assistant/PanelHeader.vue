<template>
  <!-- 面板顶部栏：头像 + 名称 + 状态指示器 + 操作按钮。Panel header: avatar + name + status indicator + action buttons. -->
  <div class="panel-header">
    <!-- 助手头像。Assistant avatar. -->
    <span class="ph-avatar"><Icon name="brain" :size="16" /></span>
    <span class="ph-name">衍衡</span>
    <!-- 清空对话按钮。Clear conversation button. -->
    <button class="ph-btn" title="清空对话" @click="emit('clear')"><Icon name="trash" :size="14" /></button>
    <!-- 关闭面板按钮。Close panel button. -->
    <button class="ph-btn" title="关闭" @click="emit('close')"><Icon name="close" :size="14" /></button>
  </div>
</template>

<script setup lang="ts">
import Icon from '../Icon.vue'
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
/* 操作按钮（清空/关闭）。Action buttons (clear/close). */
.ph-btn {
  background: none; border: none; color: var(--text-2); cursor: pointer;
  padding: 5px; border-radius: 8px; display: flex; flex-shrink: 0;
  transition: color var(--dur-fast), background var(--dur-fast);
}
.ph-btn:hover { background: rgba(51, 65, 85, .55); color: var(--text-1); }
</style>
