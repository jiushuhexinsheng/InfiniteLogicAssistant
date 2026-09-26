<template>
  <input
    class="ui-input"
    :value="modelValue"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    v-bind="$attrs"
  />
</template>

<!-- 文本输入框组件，支持 v-model 双向绑定。Text input field with v-model two-way binding. -->
<script setup lang="ts">
/** 输入框 Props：绑定值/占位文本/输入类型/是否禁用；Emits `update:modelValue` 实现 v-model。Input props: bound value, placeholder, input type, disabled; emits `update:modelValue` for v-model. */
withDefaults(defineProps<{ modelValue?: string; placeholder?: string; type?: string; disabled?: boolean }>(), { modelValue: '', placeholder: '', type: 'text', disabled: false })
defineEmits<{ 'update:modelValue': [v: string] }>()
</script>

<style scoped>
.ui-input {
  width: 100%; background: var(--surface-input);
  border: 1px solid var(--border-base); border-radius: var(--r-md);
  color: var(--text-1); padding: 10px 12px; font-size: var(--fs-sm);
  font-family: inherit;
  min-height: var(--min-target-size); /* 确保最小点击目标 */
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.ui-input::placeholder { color: var(--text-3); }

/* 焦点样式 - 使用 :focus-visible 确保键盘导航可见 */
.ui-input:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
  border-color: var(--brand-c2);
  box-shadow: 0 0 0 3px rgba(103, 232, 249, .2);
}

/* 鼠标点击时的焦点样式 */
.ui-input:focus:not(:focus-visible) {
  border-color: var(--brand-c2);
  box-shadow: 0 0 0 1px rgba(103, 232, 249, .25);
}

.ui-input:disabled { opacity: .5; cursor: not-allowed; }
</style>
