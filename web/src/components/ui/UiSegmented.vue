<template>
  <!-- 胶囊分段单选条：等宽选项、选中高亮、radiogroup 无障碍语义。
       Segmented pill radio: equal-width options, active highlight, radiogroup semantics. -->
  <div class="ui-segmented" role="radiogroup" :aria-label="ariaLabel" v-bind="$attrs">
    <button
      v-for="o in options"
      :key="o.value"
      class="sg-item"
      :class="{ on: o.value === modelValue }"
      type="button"
      role="radio"
      :aria-checked="o.value === modelValue"
      :disabled="disabled"
      @click="pick(o.value)"
    >{{ o.label }}</button>
  </div>
</template>

<!-- 分段单选组件：options 驱动，v-model 绑定选中值。Segmented radio: options-driven with v-model. -->
<script setup lang="ts">
/** 单选项。Segmented option. */
export interface SegOption {
  /** 选项值。Option value. */
  value: string
  /** 选项显示文本。Option label. */
  label: string
}

/** 分段单选 Props：选项列表/当前值/无障碍名称/是否禁用。Segmented props: options, current value, aria label, disabled. */
withDefaults(defineProps<{
  options: SegOption[]
  modelValue?: string
  ariaLabel?: string
  disabled?: boolean
}>(), { modelValue: '', ariaLabel: '单选', disabled: false })

/** 事件：选中值变更。Event: selection changed. */
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

/**
 * 选择选项。Pick an option.
 *
 * @param v 选中值。Picked value.
 */
function pick(v: string) {
  emit('update:modelValue', v)
}
</script>

<style scoped>
.ui-segmented {
  display: flex; gap: 6px;
  padding: 4px;
  background: var(--bg-2);
  border: 1px solid var(--border-base);
  border-radius: var(--r-full);
}
.sg-item {
  flex: 1; min-width: 0;
  font-family: inherit; font-size: var(--fs-xs); font-weight: 500;
  color: var(--text-2); background: transparent;
  border: none; border-radius: var(--r-full);
  padding: var(--sp-2) var(--sp-3);
  cursor: pointer;
  min-height: var(--min-target-size);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: color var(--dur-fast), background var(--dur-fast),
    box-shadow var(--dur-base) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.sg-item:hover:not(:disabled):not(.on) { color: var(--text-1); }
.sg-item:active:not(:disabled) { transform: scale(.96); }
/* 选中：品牌底 + 发光 + 按下微弹反馈。
   Active: brand fill + glow + press micro-bounce feedback. */
.sg-item.on {
  background: var(--brand-c2);
  color: var(--text-on-brand);
  font-weight: 600;
  box-shadow: 0 0 10px rgba(34, 211, 238, .35);
}
.sg-item:disabled { opacity: .5; cursor: not-allowed; }
@media (prefers-reduced-motion: reduce) {
  .sg-item { transition: none; }
  .sg-item:active:not(:disabled) { transform: none; }
}
</style>
