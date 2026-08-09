<template>
  <div class="panel-header">
    <span class="ph-avatar"><Icon name="brain" :size="16" /></span>
    <span class="ph-name">小逻</span>
    <span class="ph-status">
      <span class="ph-dot" :style="{ background: visual.color }"></span>
      <span class="ph-text">{{ statusText }}</span>
    </span>
    <button class="ph-btn" title="清空对话" @click="emit('clear')"><Icon name="trash" :size="14" /></button>
    <button class="ph-btn" title="关闭" @click="emit('close')"><Icon name="close" :size="14" /></button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Icon from '../Icon.vue'
import { resolveStateLabel } from '../../composables/useAssistantVisuals'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  visual: StateVisual
  state: AsstState
  wakeKeyword: string
}>()

const emit = defineEmits<{ clear: []; close: [] }>()

const statusText = computed(() => resolveStateLabel(props.visual, props.wakeKeyword))
</script>

<style scoped>
.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #0f172a;
  border-bottom: 1px solid var(--border-base);
}
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
.ph-name { font-size: 14px; font-weight: 600; color: var(--text-1); white-space: nowrap; }
.ph-status { flex: 1; display: flex; align-items: center; gap: 6px; min-width: 0; }
.ph-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ph-text { font-size: 12px; color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ph-btn {
  background: none; border: none; color: var(--text-2); cursor: pointer;
  padding: 4px; border-radius: 6px; display: flex; flex-shrink: 0;
}
.ph-btn:hover { background: #334155; color: var(--text-1); }
</style>
