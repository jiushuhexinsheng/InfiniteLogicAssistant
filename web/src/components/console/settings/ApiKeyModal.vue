<template>
  <!-- 密钥弹出框（替代 window.prompt）：安全设置/清除 API Key。API Key modal (replaces window.prompt): securely set/clear API keys. -->
  <UiModal :model-value="!!s.keyModal.value" @update:model-value="v => { if (!v) s.keyModal.value = null }" title="设置 API Key">
    <p class="cs-dialog-sub">{{ s.keyModal.value?.section }} · {{ s.keyModal.value?.profile }}</p>
    <div class="cs-key-input">
      <UiInput
        :type="s.showKey.value ? 'text' : 'password'"
        :model-value="s.keyModal.value ? s.keyModal.value.value : ''"
        @update:model-value="v => { const m = s.keyModal.value; if (m) m.value = v }"
        placeholder="粘贴 API Key（留空 = 清除）"
        autofocus
      />
      <UiButton variant="secondary" size="sm" @click="s.showKey.value = !s.showKey.value">{{ s.showKey.value ? '隐藏' : '显示' }}</UiButton>
    </div>
    <p v-if="s.keyEnvHint()" class="cs-dialog-env">
      也可通过环境变量 <code>{{ s.keyEnvHint() }}</code> 配置（优先级高于此密钥）
    </p>
    <div class="cs-dialog-btns">
      <UiButton variant="ghost" size="sm" @click="s.clearKey">清除</UiButton>
      <UiButton variant="primary" size="sm" @click="s.confirmKey">保存</UiButton>
      <UiButton variant="ghost" size="sm" @click="s.keyModal.value = null">取消</UiButton>
    </div>
  </UiModal>
</template>

<!-- 密钥弹窗：由 ConsoleSettings 编排壳挂载，状态取自 useSettings 单例。API Key modal: mounted by the ConsoleSettings shell, state from the useSettings singleton. -->
<script setup lang="ts">
import { UiButton, UiInput, UiModal } from '../../ui'
import { useSettings } from './useSettings'

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()
</script>

<style scoped>
.cs-dialog-sub { font-size: var(--fs-2xs); color: var(--text-3); margin: 0; font-family: var(--font-mono); }
.cs-key-input { display: flex; align-items: center; gap: 8px; }
.cs-key-input :deep(.ui-input) { flex: 1; min-width: 0; }
.cs-dialog-env { font-size: var(--fs-2xs); color: var(--text-3); margin: 0; line-height: 1.6; }
.cs-dialog-env code { font-family: var(--font-mono); color: var(--brand-c2); }
.cs-dialog-btns { display: flex; justify-content: flex-end; gap: 8px; }
</style>
