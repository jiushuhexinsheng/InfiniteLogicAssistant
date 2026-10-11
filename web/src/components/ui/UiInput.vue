<template>
  <!-- 数字输入：自绘步进器（隐藏浏览器原生 spinner，圆钮风格对齐 UiSelect 的
       chevron 底座）；文本输入保持单根 <input>，落点与旧版完全一致。
     Number input: custom stepper (native browser spinners hidden; round buttons
     styled after UiSelect's chevron seat); text input keeps the bare <input> root,
     identical to before. -->
  <div v-if="type === 'number'" class="ui-stepper">
    <input
      class="ui-input ui-stepper-input"
      :value="modelValue"
      type="number"
      :placeholder="placeholder"
      :disabled="disabled"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      @keydown="onKeydown"
      v-bind="$attrs"
    />
    <span class="ui-stepper-btns">
      <button type="button" class="ui-stepper-btn" :disabled="disabled" aria-label="增加" @click="bump(1)">
        <UiIcon name="chevron-down" :size="11" class="ui-stepper-up" />
      </button>
      <button type="button" class="ui-stepper-btn" :disabled="disabled" aria-label="减少" @click="bump(-1)">
        <UiIcon name="chevron-down" :size="11" />
      </button>
    </span>
  </div>
  <input
    v-else
    class="ui-input"
    :value="modelValue"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    v-bind="$attrs"
  />
</template>

<!-- 文本/数字输入框组件，v-model 双向绑定（数字型带自绘步进器）。
     Text/number input with v-model (the number variant carries a custom stepper). -->
<script setup lang="ts">
import { useAttrs } from 'vue'
import UiIcon from './UiIcon.vue'

/**
 * 组件 Props：绑定值/占位/类型/禁用。`step`/`min`/`max` 经 $attrs 透传（数字步进器读取）。
 * Emits `update:modelValue` 实现 v-model（值始终以字符串外发，调用方 toNum 转换不变）。
 *
 * Props: value, placeholder, type, disabled. `step`/`min`/`max` pass through via $attrs
 * (the stepper reads them). Emits `update:modelValue` for v-model (always emitted as a
 * string; call sites' toNum conversion is unchanged).
 */
const props = withDefaults(
  defineProps<{ modelValue?: string | number; placeholder?: string; type?: string; disabled?: boolean }>(),
  { modelValue: '', placeholder: '', type: 'text', disabled: false },
)
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()
const attrs = useAttrs()
// 条件根（number 分支是 div）→ 关闭自动属性落下，$attrs 已显式绑到内层 input。
// Conditional root (the number branch is a div) → disable automatic fallthrough;
// $attrs is explicitly bound to the inner input in both branches.
defineOptions({ inheritAttrs: false })

/** 是否数字型（渲染自绘步进器分支）。Whether this is the number variant. */
const isNumber = props.type === 'number'

/**
 * 步进：按 attrs.step 增减并夹在 min/max 内（小数位数对齐 step，避免 0.1+0.2 漂移）。
 * Step by attrs.step, clamped to min/max (decimals aligned to step — no 0.1+0.2 drift).
 */
function bump(dir: 1 | -1) {
  const step = Number((attrs as any).step) || 1
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
  const minRaw = (attrs as any).min
  const maxRaw = (attrs as any).max
  const min = minRaw !== undefined && minRaw !== '' && !Number.isNaN(Number(minRaw)) ? Number(minRaw) : -Infinity
  const max = maxRaw !== undefined && maxRaw !== '' && !Number.isNaN(Number(maxRaw)) ? Number(maxRaw) : Infinity
  const cur = Number(props.modelValue)
  const base = Number.isFinite(cur) ? cur : (Number.isFinite(min) ? min : 0)
  const dec = (String(step).split('.')[1] || '').length
  const next = Number(clamp(base + dir * step, min, max).toFixed(dec))
  emit('update:modelValue', String(next))
}

/** 键盘 ↑↓ 代替被隐藏的原生 spinner。Arrow keys replace the hidden native spinners. */
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowUp') { e.preventDefault(); bump(1) }
  else if (e.key === 'ArrowDown') { e.preventDefault(); bump(-1) }
}
</script>

<style scoped>
/* 文本输入（与旧版一致，单根落点不变）。Text input (unchanged, same single root). */
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

/* ── 数字步进器：隐藏原生 spinner，自绘圆钮（风格对齐 UiSelect chevron 底座） ──
   Number stepper: native spinners hidden, round buttons drawn to match UiSelect's
   chevron seat. */
.ui-stepper { position: relative; width: 100%; flex: 1 1 auto; min-width: 0; }
.ui-stepper-input { padding-right: 34px; }
/* 隐藏浏览器原生上下按钮（各平台外观不一、与暗色玻璃风割裂）。
   Hide the browser's native up/down buttons (platform-inconsistent, clashes with the
   dark-glass look). */
.ui-stepper-input::-webkit-outer-spin-button,
.ui-stepper-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.ui-stepper-input[type='number'] { -moz-appearance: textfield; appearance: textfield; }

.ui-stepper-btns {
  position: absolute; right: 5px; top: 50%;
  transform: translateY(-50%);
  display: flex; flex-direction: column; gap: 2px;
  pointer-events: none; /* 空隙不截点击，按钮自身再开。Gaps never swallow clicks; buttons opt in. */
}
.ui-stepper-btn {
  pointer-events: auto;
  width: 24px; height: 15px;
  display: grid; place-items: center;
  border: none; padding: 0; cursor: pointer;
  background: var(--surface-control); color: var(--text-3);
  border-radius: 4px;
  transition: color var(--dur-fast), background var(--dur-fast);
}
.ui-stepper-btn:hover:not(:disabled) { color: var(--brand-c2); background: rgba(103, 232, 249, .12); }
.ui-stepper-btn:disabled { opacity: .4; cursor: not-allowed; }
.ui-stepper-up { transform: rotate(180deg); }
</style>
