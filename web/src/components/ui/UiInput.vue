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

<!-- 文本输入框组件，支持 v-model 双向绑定。Text input field with v-model two-way binding. -->
<script setup lang="ts">
/** 输入框 Props：绑定值/占位文本/输入类型/是否禁用；Emits `update:modelValue` 实现 v-model。Input props: bound value, placeholder, input type, disabled; emits `update:modelValue` for v-model. */
withDefaults(defineProps<{ modelValue?: string; placeholder?: string; type?: string; disabled?: boolean }>(), { modelValue: '', placeholder: '', type: 'text', disabled: false })
defineEmits<{ 'update:modelValue': [v: string] }>()
</script>

<style scoped>
/* 输入框：凹陷层次 + 加大圆角 + focus 品牌光晕常驻。
   Input: inset depth + larger radius + persistent brand focus glow. */
.ui-input {
  width: 100%; background: var(--surface-input);
  border: 1px solid var(--border-base); border-radius: var(--r-lg);
  color: var(--text-1); padding: 10px 12px; font-size: var(--fs-sm);
  font-family: inherit;
  min-height: var(--min-target-size); /* 确保最小点击目标 */
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, .35);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.ui-input::placeholder { color: var(--text-3); }
/* hover 需避开 focus —— 否则特异性更高的半透明 hover 边框会盖掉 focus 实色边框，
   光晕旁的边框发暗，视觉上「光晕没贴合边框」。
   hover must yield to focus — the higher-specificity translucent hover border would
   otherwise cover focus's solid border, leaving the glow visually detached. */
.ui-input:hover:not(:disabled):not(:focus) { border-color: rgba(103, 232, 249, .45); }

/* 焦点：青色描边 + 光晕常驻（含鼠标点击）。Focus: brand border + glow, persistent (mouse included). */
.ui-input:focus {
  outline: none;
  border-color: var(--brand-c2);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, .35), var(--focus-glow);
}

.ui-input:disabled { opacity: .5; cursor: not-allowed; }
</style>
