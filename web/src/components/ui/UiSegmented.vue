<template>
  <!-- 胶囊分段单选条：等宽选项、选中高亮、radiogroup 无障碍语义。
       Segmented pill radio: equal-width options, active highlight, radiogroup semantics. -->
  <div class="ui-segmented" :class="layout" role="radiogroup" :aria-label="ariaLabel" v-bind="$attrs">
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
    >
      <span class="sg-zh">{{ o.label }}</span>
      <span v-if="showEn(o)" class="sg-en">{{ o.en }}</span>
    </button>
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
  /** 可选的英文副标签（stack 布局下显示）。Optional English subtitle (stack layout). */
  en?: string
}

/** 分段单选 Props：选项列表/当前值/无障碍名称/是否禁用。Segmented props: options, current value, aria label, disabled. */
const props = withDefaults(defineProps<{
  options: SegOption[]
  modelValue?: string
  ariaLabel?: string
  disabled?: boolean
  layout?: 'inline' | 'stack'
}>(), { modelValue: '', ariaLabel: '单选', disabled: false, layout: 'inline' })

/** 事件：选中值变更。Event: selection changed. */
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

/** 英文是否显示：仅 stack 且与中文不同。Whether to show the English subtitle. */
function showEn(option: SegOption): boolean {
  return props.layout === 'stack' && !!option.en && option.en !== option.label
}

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
  display: flex; gap: var(--sp-q6);
  padding: var(--sp-1);
  background: var(--bg-2);
  border: 1px solid var(--border-base);
  border-radius: var(--r-full);
}
.ui-segmented.stack .sg-item { flex-direction: column; gap: 1px; line-height: 1.15; }
.sg-en { font-size: var(--fs-2xs); color: var(--text-3); font-weight: 400; white-space: nowrap; }
.sg-item {
  flex: 1; min-width: 0;
  display: inline-flex; align-items: center; justify-content: center;
  flex-direction: row; gap: var(--sp-q6);
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
  .ui-segmented.stack .sg-item { flex-direction: column; gap: 1px; line-height: 1.15; }
.sg-en { font-size: var(--fs-2xs); color: var(--text-3); font-weight: 400; white-space: nowrap; }
.sg-item { transition: none; }
  .sg-item:active:not(:disabled) { transform: none; }
}
</style>
