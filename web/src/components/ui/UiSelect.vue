<template>
  <div class="ui-select-wrap">
    <select class="ui-select" :value="modelValue" :disabled="disabled" @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)" v-bind="$attrs">
      <slot />
    </select>
    <UiIcon name="chevron-down" :size="14" class="ui-select-chevron" />
  </div>
</template>

<!-- 下拉选择框组件，隐藏原生样式并自定义箭头图标。Custom-styled select dropdown with native appearance hidden. -->
<script setup lang="ts">
import UiIcon from './UiIcon.vue'
/** 选择框 Props：选中值(v-model)/是否禁用；Emits `update:modelValue`。Select props: selected value (v-model), disabled; emits `update:modelValue`. */
withDefaults(defineProps<{ modelValue?: string; disabled?: boolean }>(), { modelValue: '', disabled: false })
defineEmits<{ 'update:modelValue': [v: string] }>()
</script>

<style scoped>
.ui-select-wrap { position: relative; display: inline-flex; width: 100%; }
.ui-select {
  width: 100%; appearance: none; -webkit-appearance: none;
  background: var(--surface-input); border: 1px solid var(--border-base); border-radius: var(--r-md);
  color: var(--text-1); padding: 10px 30px 10px 12px; font-size: var(--fs-sm); font-family: inherit;
  cursor: pointer;
  min-height: var(--min-target-size);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.ui-select::placeholder { color: var(--text-3); }

/* 焦点样式 - 使用 :focus-visible 确保键盘导航可见 */
.ui-select:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
  border-color: var(--brand-c2);
  box-shadow: 0 0 0 3px rgba(103, 232, 249, .2);
}

/* 鼠标点击时的焦点样式 */
.ui-select:focus:not(:focus-visible) {
  border-color: var(--brand-c2);
  box-shadow: 0 0 0 1px rgba(103, 232, 249, .25);
}

.ui-select:disabled { opacity: .5; cursor: not-allowed; }
.ui-select-chevron { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); color: var(--text-3); pointer-events: none; }
</style>
