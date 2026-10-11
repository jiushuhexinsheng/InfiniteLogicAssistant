<template>
  <!-- 数字输入：外层 div 即「可见字段」（边框/底色/聚焦光晕都在它身上），按钮用 flex
       排在内侧右缘 —— 结构上不可能跑到字段外面（绝对定位在某些嵌套布局下会以卡片为
       定位父级，按钮漂到卡片右缘）。浏览器原生 spinner 隐藏。
     Number input: the wrapper div IS the visible field (border/background/focus glow all
     live on it) and the buttons sit on the inner right edge via flex — structurally
     unable to escape the field (absolute positioning can resolve against the card in
     some nesting layouts and drift to the card's right edge). Native spinners hidden. -->
  <div v-if="type === 'number'" class="ui-stepper">
    <input
      class="ui-input ui-stepper-input"
      :value="modelValue"
      type="number"
      :placeholder="placeholder"
      :disabled="disabled"
      autocomplete="off"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      @keydown="onKeydown"
      v-bind="$attrs"
    />
    <span class="ui-stepper-btns">
      <button type="button" class="ui-stepper-btn" :disabled="disabled" aria-label="增加" @click="bump(1)">
        <UiIcon name="chevron-down" :size="9" class="ui-stepper-up" />
      </button>
      <button type="button" class="ui-stepper-btn" :disabled="disabled" aria-label="减少" @click="bump(-1)">
        <UiIcon name="chevron-down" :size="9" />
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
    autocomplete="off"
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

/* ── 数字步进器：外层 = 可见字段（与 .ui-input 同款外观/聚焦光晕），按钮 flex 内嵌 ──
   Number stepper: the wrapper IS the visible field (same look/focus glow as .ui-input),
   buttons flexed inside — they cannot escape the field's border. */
.ui-stepper {
  display: flex; align-items: center; gap: 6px;
  width: 100%; flex: 1 1 auto; min-width: 0;
  /* 高度与文本输入严格同值（同一变量钉死）——内层不再自带纵向 padding，
     由外层统一决定，避免数字框比其它框高。
     Height pinned to the exact same value as text inputs (one shared token) — the inner
     input carries no vertical padding any more, so the number field can never grow
     taller than its siblings. */
  min-height: var(--min-target-size);
  height: var(--min-target-size);
  padding: 0 6px 0 12px;
  background: var(--surface-input);
  border: 1px solid var(--border-base);
  border-radius: var(--r-lg);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, .35);
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.ui-stepper:hover:not(:focus-within) {
  border-color: rgba(103, 232, 249, .45);
}
.ui-stepper:focus-within {
  border-color: var(--brand-c2);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, .35), var(--focus-glow);
}
/* 内部输入透明化：外观全部交给外层，避免双层边框。
   The inner input is transparent: all appearance belongs to the wrapper (no double border). */
.ui-stepper-input {
  flex: 1 1 auto; min-width: 0;
  background: transparent; border: none; outline: none;
  box-shadow: none !important;
  padding: 0;                    /* 纵向 padding 归外层管，保证与文本框同高。Vertical padding belongs to the wrapper (same height as text fields). */
  height: 100%;
  font-size: var(--fs-sm); font-family: inherit; color: var(--text-1);
  min-height: 0;
}
.ui-stepper-input:focus { border-color: transparent; }
.ui-stepper-input:disabled { opacity: .5; }
/* 隐藏浏览器原生上下按钮（各平台外观不一、与暗色玻璃风割裂）。
   Hide the browser's native up/down buttons (platform-inconsistent, clashes with the
   dark-glass look). */
.ui-stepper-input::-webkit-outer-spin-button,
.ui-stepper-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.ui-stepper-input[type='number'] { -moz-appearance: textfield; appearance: textfield; }

.ui-stepper-btns {
  display: flex; flex-direction: column; gap: 1px;
  flex: 0 0 auto;
}
.ui-stepper-btn {
  width: 16px; height: 12px;
  display: grid; place-items: center;
  border: none; padding: 0; cursor: pointer;
  background: var(--surface-control); color: var(--text-3);
  border-radius: 3px;
  transition: color var(--dur-fast), background var(--dur-fast);
}
.ui-stepper-btn:hover:not(:disabled) { color: var(--brand-c2); background: rgba(103, 232, 249, .12); }
.ui-stepper-btn:disabled { opacity: .4; cursor: not-allowed; }
.ui-stepper-up { transform: rotate(180deg); }
</style>
