<template>
  <!-- 大图形单选卡组：图标 + 标题 + 副文案，选中描边高亮，radiogroup 语义。
       Graphic radio card group: icon + title + hint, active border highlight, radiogroup semantics. -->
  <div class="ui-radio-cards" role="radiogroup" :aria-label="ariaLabel" v-bind="$attrs">
    <button
      v-for="o in options"
      :key="o.value"
      class="rc-card"
      :class="{ on: o.value === modelValue }"
      type="button"
      role="radio"
      :aria-checked="o.value === modelValue"
      :disabled="disabled"
      @click="pick(o.value)"
    >
      <UiIcon v-if="o.icon" :name="o.icon" :size="20" />
      <b>{{ o.label }}</b>
      <em>{{ o.hint }}</em>
    </button>
  </div>
</template>

<!-- 大图形单选组件：options 驱动（value/icon/label/hint），v-model 绑定。Graphic radio: options-driven, v-model. -->
<script setup lang="ts">
import UiIcon from './UiIcon.vue'

/** 单选卡选项。Radio card option. */
export interface RadioCardOption {
  /** 选项值。Option value. */
  value: string
  /** 图标名（UiIcon）。Icon name (UiIcon). */
  icon?: string
  /** 主标题。Title. */
  label: string
  /** 副文案。Hint text. */
  hint: string
}

/** 单选卡 Props：选项列表/当前值/无障碍名称/是否禁用。Radio card props: options, value, aria label, disabled. */
withDefaults(defineProps<{
  options: RadioCardOption[]
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
.ui-radio-cards { display: flex; gap: 10px; }
.rc-card {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column; align-items: center; gap: 5px;
  padding: 16px 10px 14px;
  border-radius: var(--r-lg);
  background: rgba(15, 23, 42, .6);
  border: 1px solid var(--border-soft);
  color: var(--text-3);
  cursor: pointer; font-family: inherit;
  transition: border-color var(--dur-fast), background var(--dur-fast), color var(--dur-fast),
    transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-base) var(--ease-out);
}
.rc-card b { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); }
.rc-card em {
  font-style: normal; font-size: var(--fs-2xs);
  color: var(--text-3); letter-spacing: .02em;
}
.rc-card:hover:not(:disabled):not(.on) { border-color: var(--brand-c2); transform: translateY(-2px); }
.rc-card:active:not(:disabled) { transform: scale(.98); }
/* 选中：描边 + 青色底 + 外发光。Active: brand border + cyan tint + outer glow. */
.rc-card.on {
  border-color: var(--brand-c2);
  background: rgba(103, 232, 249, .1);
  box-shadow: 0 0 0 1px rgba(103, 232, 249, .25), 0 0 14px rgba(34, 211, 238, .28);
}
.rc-card.on :deep(svg) { color: var(--brand-c2); }
.rc-card.on b { color: var(--brand-c2); }
.rc-card:disabled { opacity: .5; cursor: not-allowed; }
@media (prefers-reduced-motion: reduce) {
  .rc-card { transition: none; }
  .rc-card:hover:not(:disabled):not(.on) { transform: none; }
  .rc-card:active:not(:disabled) { transform: none; }
}
</style>
