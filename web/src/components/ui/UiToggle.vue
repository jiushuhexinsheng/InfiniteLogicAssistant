<template>
  <button
    class="ui-toggle"
    :class="{ on: modelValue }"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    type="button"
    @click="$emit('update:modelValue', !modelValue)"
  >
    <span class="ui-toggle-knob"></span>
  </button>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ modelValue: boolean; disabled?: boolean }>(), { disabled: false })
defineEmits<{ 'update:modelValue': [v: boolean] }>()
</script>

<style scoped>
.ui-toggle {
  width: 40px; height: 22px; border-radius: 11px; border: none; cursor: pointer;
  background: var(--bg-3); display: flex; align-items: center; padding: 3px;
  transition: background var(--dur-base);
}
.ui-toggle.on { background: var(--brand-c2); justify-content: flex-end; }
.ui-toggle:disabled { opacity: .5; cursor: not-allowed; }
.ui-toggle-knob { width: 16px; height: 16px; border-radius: 50%; background: #fff; box-shadow: var(--shadow-1); }
</style>
