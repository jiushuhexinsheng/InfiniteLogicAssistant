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

<!-- 开关切换组件，使用 role="switch" 语义化无障碍属性。Toggle switch with semantic `role="switch"` for accessibility. -->
<script setup lang="ts">
/** 切换开关 Props：当前开关状态(v-model)/是否禁用；Emits `update:modelValue` 切换布尔值。Toggle props: current on/off state (v-model), disabled; emits `update:modelValue` to flip boolean. */
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
