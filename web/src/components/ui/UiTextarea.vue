<template>
  <textarea
    ref="el"
    class="ui-textarea"
    :value="modelValue"
    :rows="rows"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="onInput"
    v-bind="$attrs"
  ></textarea>
</template>

<!-- 多行文本域组件：v-model 绑定、可调行数、可选自动增高（上限 maxRows）。Multi-line textarea: v-model, configurable rows, optional autosize (capped at maxRows). -->
<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

/** 文本域 Props：绑定值/默认行数/占位文本/禁用/自动增高/最大行数。Textarea props: bound value, rows, placeholder, disabled, autosize, max rows. */
const props = withDefaults(defineProps<{
  modelValue?: string
  rows?: number
  placeholder?: string
  disabled?: boolean
  autosize?: boolean
  maxRows?: number
}>(), { modelValue: '', rows: 2, placeholder: '', disabled: false, autosize: false, maxRows: 4 })

/** 事件：值变更。Event: value changed. */
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

/** textarea 元素引用。Textarea element ref. */
const el = ref<HTMLTextAreaElement>()

/**
 * 自动调整高度：重置为 auto 后按 scrollHeight 收敛到 maxRows 行高上限。
 * Autosize: reset to auto, then cap scrollHeight at maxRows lines.
 */
function autosize() {
  const node = el.value
  if (!node || !props.autosize) return
  node.style.height = 'auto'
  const lineHeight = parseFloat(getComputedStyle(node).lineHeight) || 20
  node.style.height = Math.min(node.scrollHeight, props.maxRows * lineHeight) + 'px'
}

/**
 * 输入回调：转发值并触发自动增高。
 * Input handler: forward value and trigger autosize.
 *
 * @param e 原生输入事件。Native input event.
 */
function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
  nextTick(autosize)
}

// 外部改值（如提交清空）后同步收敛高度。Converge height after external value changes (e.g. clear-on-submit).
watch(() => props.modelValue, () => nextTick(autosize))
</script>

<style scoped>
/* 文本域：凹陷层次 + 加大圆角 + focus 品牌光晕常驻。
   Textarea: inset depth + larger radius + persistent brand focus glow. */
.ui-textarea {
  width: 100%; resize: vertical; background: var(--surface-input);
  border: 1px solid var(--border-base); border-radius: var(--r-lg);
  color: var(--text-1); padding: 10px 12px; font-size: var(--fs-sm);
  font-family: inherit; line-height: 1.5;
  min-height: var(--min-target-size);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, .35);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.ui-textarea::placeholder { color: var(--text-3); }
/* hover 需避开 focus（同 UiInput：防止半透明边框盖掉 focus 实色边框）。
   hover yields to focus (same as UiInput: translucent border must not cover focus's solid border). */
.ui-textarea:hover:not(:disabled):not(:focus) { border-color: rgba(103, 232, 249, .45); }

/* 焦点：青色描边 + 光晕常驻（含鼠标点击）。Focus: brand border + glow, persistent (mouse included). */
.ui-textarea:focus {
  outline: none;
  border-color: var(--brand-c2);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, .35), var(--focus-glow);
}

.ui-textarea:disabled { opacity: .5; cursor: not-allowed; }
</style>
