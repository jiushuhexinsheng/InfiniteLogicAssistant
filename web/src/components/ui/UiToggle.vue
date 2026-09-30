<template>
  <button
    class="ui-toggle"
    :class="{ on: modelValue }"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="ariaLabel"
    :disabled="disabled"
    type="button"
    v-bind="$attrs"
    @click="$emit('update:modelValue', !modelValue)"
  >
    <span class="ui-toggle-knob"></span>
  </button>
</template>

<!-- 开关切换组件，使用 role="switch" 语义化无障碍属性。Toggle switch with semantic `role="switch"` for accessibility. -->
<script setup lang="ts">
/** 切换开关 Props：当前开关状态(v-model)/是否禁用/无障碍标签；Emits `update:modelValue` 切换布尔值。Toggle props: current on/off state (v-model), disabled, aria-label; emits `update:modelValue` to flip boolean. */
withDefaults(defineProps<{
  modelValue: boolean
  disabled?: boolean
  ariaLabel?: string
}>(), { disabled: false, ariaLabel: '切换开关' })
defineEmits<{ 'update:modelValue': [v: boolean] }>()
</script>

<style scoped>
.ui-toggle {
  width: 44px; height: 24px; border-radius: 12px; border: none; cursor: pointer;
  background: var(--bg-3); display: flex; align-items: center; padding: 3px;
  min-height: var(--min-target-size); min-width: var(--min-target-size);
  transition: background var(--dur-base), box-shadow var(--dur-base) var(--ease-out);
}
/* 打开：品牌底 + 发光。On: brand fill + glow. */
.ui-toggle.on {
  background: var(--brand-c2);
  justify-content: flex-end;
  box-shadow: 0 0 10px rgba(34, 211, 238, .45);
}
.ui-toggle:disabled { opacity: .5; cursor: not-allowed; }
.ui-toggle-knob { width: 18px; height: 18px; border-radius: 50%; background: #fff; box-shadow: var(--shadow-1); }

/* 焦点样式 */
.ui-toggle:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}
</style>
