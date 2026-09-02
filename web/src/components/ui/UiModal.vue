<template>
  <Teleport to="body">
    <Transition name="ui-modal">
      <div v-if="modelValue" class="ui-modal-overlay" @click.self="$emit('update:modelValue', false)">
        <div class="ui-modal" role="dialog" aria-modal="true">
          <div class="ui-modal-head">
            <span class="ui-modal-title"><slot name="title">{{ title }}</slot></span>
            <button class="ui-modal-close" type="button" @click="$emit('update:modelValue', false)"><UiIcon name="close" :size="14" /></button>
          </div>
          <div class="ui-modal-body"><slot /></div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<!-- 模态对话框组件，通过 Teleport 挂载到 body，点击遮罩层可关闭。Modal dialog, teleported to body; closes on overlay click. -->
<script setup lang="ts">
import UiIcon from './UiIcon.vue'
/** 模态框 Props：显示/隐藏状态(v-model)/标题文本；Emits `update:modelValue` 控制开关。Modal props: visibility (v-model), title text; emits `update:modelValue` to toggle. */
withDefaults(defineProps<{ modelValue: boolean; title?: string }>(), { title: '' })
defineEmits<{ 'update:modelValue': [v: boolean] }>()
</script>

<style scoped>
.ui-modal-overlay {
  position: fixed; inset: 0; z-index: 9990;
  display: flex; align-items: center; justify-content: center;
  background: rgba(2, 6, 23, .6); backdrop-filter: blur(6px);
  padding: 24px;
}
.ui-modal {
  width: min(520px, 92vw); max-height: 80vh; overflow: auto;
  border: 1px solid var(--glass-border); border-radius: var(--r-xl);
  background: var(--surface-raised); backdrop-filter: blur(18px) saturate(140%);
  box-shadow: var(--shadow-3);
  display: flex; flex-direction: column;
}
.ui-modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border-bottom: 1px solid var(--border-soft);
}
.ui-modal-title { font-size: var(--fs-md); font-weight: 600; color: var(--text-1); }
.ui-modal-close {
  display: flex; align-items: center; justify-content: center;
  background: none; border: none; color: var(--text-2); cursor: pointer;
  padding: 4px; border-radius: 6px;
}
.ui-modal-close:hover { background: var(--bg-3); color: var(--text-1); }
.ui-modal-body { padding: 16px; }
.ui-modal-enter-active, .ui-modal-leave-active { transition: opacity .2s ease, transform .2s ease; }
.ui-modal-enter-from, .ui-modal-leave-to { opacity: 0; transform: translateY(12px) scale(.97); }
</style>
