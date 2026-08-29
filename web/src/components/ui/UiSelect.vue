<template>
  <div class="ui-select-wrap">
    <select class="ui-select" :value="modelValue" :disabled="disabled" @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)" v-bind="$attrs">
      <slot />
    </select>
    <UiIcon name="chevron-down" :size="14" class="ui-select-chevron" />
  </div>
</template>

<script setup lang="ts">
import UiIcon from './UiIcon.vue'
withDefaults(defineProps<{ modelValue?: string; disabled?: boolean }>(), { modelValue: '', disabled: false })
defineEmits<{ 'update:modelValue': [v: string] }>()
</script>

<style scoped>
.ui-select-wrap { position: relative; display: inline-flex; width: 100%; }
.ui-select {
  width: 100%; appearance: none; -webkit-appearance: none;
  background: var(--surface-input); border: 1px solid var(--border-base); border-radius: var(--r-md);
  color: var(--text-1); padding: 8px 30px 8px 12px; font-size: var(--fs-sm); font-family: inherit;
  outline: none; cursor: pointer;
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.ui-select:focus { border-color: var(--brand-c2); box-shadow: 0 0 0 1px rgba(103, 232, 249, .25); }
.ui-select:disabled { opacity: .5; cursor: not-allowed; }
.ui-select-chevron { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); color: var(--text-3); pointer-events: none; }
</style>
