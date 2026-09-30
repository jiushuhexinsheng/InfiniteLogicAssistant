<template>
  <!-- 范围滑块：标签 + 右侧格式化值 + 渐变轨道滑轨。
       Range slider: label + right-aligned formatted value + gradient track. -->
  <label class="ui-range" v-bind="$attrs">
    <span class="ur-label">
      <span>{{ label }}</span>
      <em v-if="valueText">{{ valueText }}</em>
    </span>
    <input
      class="ur-input"
      type="range"
      :min="min"
      :max="max"
      :step="step"
      :value="modelValue"
      @input="onInput"
      @change="$emit('change')"
    />
  </label>
</template>

<!-- 范围滑块组件：v-model 数值绑定，change 事件用于持久化触发。Range slider: numeric v-model; change event fires for persistence. -->
<script setup lang="ts">
/** 滑块 Props：当前值/最小值/最大值/步长/标签/右侧格式化值。Slider props: value, min, max, step, label, formatted value text. */
withDefaults(defineProps<{
  modelValue?: number
  min?: number
  max?: number
  step?: number
  label?: string
  valueText?: string
}>(), { modelValue: 0, min: 0, max: 1, step: 1, label: '', valueText: '' })

/** 事件：值变更（input 即时）与 change（释放，供持久化）。Events: value update (on input) and change (on release, for persistence). */
const emit = defineEmits<{ 'update:modelValue': [v: number]; change: [] }>()

/**
 * 输入回调：统一转 number 再发出。
 * Input handler: coerce to number before emitting.
 *
 * @param e 原生输入事件。Native input event.
 */
function onInput(e: Event) {
  emit('update:modelValue', Number((e.target as HTMLInputElement).value))
}
</script>

<style scoped>
.ui-range { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
/* 标签行：左标签右值。Label row: label left, value right. */
.ur-label {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: var(--fs-2xs); color: var(--text-3);
}
.ur-label em {
  font-style: normal; font-family: var(--font-mono);
  color: var(--brand-c2); font-size: 10px;
}

/* 滑轨：去原生外观，加粗渐变轨道 + 品牌描边拇指（带光晕）。
   Track: native look stripped, thicker gradient rail + brand-ringed glowing thumb. */
.ur-input {
  -webkit-appearance: none;
  appearance: none;
  width: 100%; height: 6px; border-radius: var(--r-full);
  background: linear-gradient(90deg, var(--brand-c1), var(--brand-c3));
  outline: none; cursor: pointer;
}
.ur-input:focus-visible {
  outline: var(--focus-ring); outline-offset: var(--focus-offset);
}
.ur-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px; height: 16px; border-radius: 50%;
  background: #fff; border: 2px solid var(--brand-c2);
  box-shadow: var(--glow-brand), 0 0 8px rgba(34, 211, 238, .5);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out);
}
.ur-input:active::-webkit-slider-thumb { transform: scale(1.15); }
.ur-input::-moz-range-thumb {
  width: 16px; height: 16px; border-radius: 50%;
  background: #fff; border: 2px solid var(--brand-c2);
  box-shadow: var(--glow-brand), 0 0 8px rgba(34, 211, 238, .5);
  cursor: pointer;
}
@media (prefers-reduced-motion: reduce) {
  .ur-input::-webkit-slider-thumb { transition: none; }
}
</style>
