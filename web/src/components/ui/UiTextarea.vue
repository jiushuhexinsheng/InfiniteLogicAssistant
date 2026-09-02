<template>
  <textarea
    class="ui-textarea"
    :value="modelValue"
    :rows="rows"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
    v-bind="$attrs"
  ></textarea>
</template>

<!-- 多行文本域组件，支持 v-model 双向绑定和可调行数。Multi-line textarea with v-model binding and configurable row count. -->
<script setup lang="ts">
/** 文本域 Props：绑定值/默认行数/占位文本/是否禁用；Emits `update:modelValue`。Textarea props: bound value, default rows, placeholder, disabled; emits `update:modelValue`. */
withDefaults(defineProps<{ modelValue?: string; rows?: number; placeholder?: string; disabled?: boolean }>(), { modelValue: '', rows: 2, placeholder: '', disabled: false })
defineEmits<{ 'update:modelValue': [v: string] }>()
</script>

<style scoped>
.ui-textarea {
  width: 100%; resize: vertical; background: var(--surface-input);
  border: 1px solid var(--border-base); border-radius: var(--r-md);
  color: var(--text-1); padding: 10px 12px; font-size: var(--fs-sm);
  font-family: inherit; outline: none; line-height: 1.5;
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.ui-textarea::placeholder { color: var(--text-3); }
.ui-textarea:focus { border-color: var(--brand-c2); box-shadow: 0 0 0 1px rgba(103, 232, 249, .25); }
.ui-textarea:disabled { opacity: .5; }
</style>
