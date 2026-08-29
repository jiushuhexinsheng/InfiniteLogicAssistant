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

<script setup lang="ts">
withDefaults(defineProps<{ modelValue?: string; placeholder?: string; type?: string; disabled?: boolean }>(), { modelValue: '', placeholder: '', type: 'text', disabled: false })
defineEmits<{ 'update:modelValue': [v: string] }>()
</script>

<style scoped>
.ui-input {
  width: 100%; background: var(--surface-input);
  border: 1px solid var(--border-base); border-radius: var(--r-md);
  color: var(--text-1); padding: 8px 12px; font-size: var(--fs-sm);
  font-family: inherit; outline: none;
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.ui-input::placeholder { color: var(--text-3); }
.ui-input:focus { border-color: var(--brand-c2); box-shadow: 0 0 0 1px rgba(103, 232, 249, .25); }
.ui-input:disabled { opacity: .5; }
</style>
