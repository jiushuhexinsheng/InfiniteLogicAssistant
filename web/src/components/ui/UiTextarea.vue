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

<script setup lang="ts">
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
