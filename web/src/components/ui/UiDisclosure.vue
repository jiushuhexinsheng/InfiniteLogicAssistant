<template>
  <!-- 折叠头：全宽触发按钮（aria-expanded）+ 旋转箭头 + 展开内容。
       Disclosure: full-width trigger (aria-expanded) + rotating chevron + expanded content. -->
  <div class="ui-disclosure">
    <!-- ⚠️ 这里**刻意没有** `aria-controls`（10.4 提过、本轮定性不加）。
         APG 的 Disclosure 模式里 `aria-expanded` 是**必需**项（本组件已有），而 `aria-controls` 是
         **可选**项 —— 原文：「Optionally, the element with role `button` has a value specified for
         `aria-controls` that refers to the element that contains all the content that is shown or
         hidden」。键盘（Enter/Space）由原生 `<button>` 天然满足。
         要加它就得给 slot 内容包一层带 id 的 div，而：
           ① 收起态那一层**根本不在 DOM 里**，指的 id 会悬空；
           ② 默认插槽允许多根，包一层在 flex/grid 父级下会改布局；
           ③ 现有的 32 张截图里**没有任何一张展开过它**（`conv-blocks` 的 thinking 块是
              `meta.collapsed: true`、UnknownBlock 硬编码 `open=false`）—— 改了也验不出来。
         三条加起来：加了是负收益。若将来真需要，先补一张「展开态」截图再说。
         ⚠️ No `aria-controls` here, deliberately. In the APG disclosure pattern `aria-expanded` is
         required (present) while `aria-controls` is explicitly optional. Adding it would need an
         extra id-carrying div around the slot content, and: (1) that div does not exist in the DOM
         while collapsed, so the reference would dangle; (2) the default slot allows multiple roots,
         and a wrapper changes layout under a flex/grid parent; (3) not one of the 32 shots ever
         expands this component. Net negative — add a shot for the expanded state first. -->
    <button
      class="ud-head"
      type="button"
      :aria-expanded="modelValue"
      @click="$emit('update:modelValue', !modelValue)"
    >
      <slot name="head" />
      <UiIcon name="chevron-down" :size="11" class="ud-chev" :class="{ rot: modelValue }" />
    </button>
    <slot v-if="modelValue" />
    <slot v-else name="collapsed" />
  </div>
</template>

<!-- 折叠组件：v-model 控制展开；head 插槽放头部内容，collapsed 插槽放折叠态预览。Collapse: v-model controls expansion; head slot for header, collapsed slot for preview when closed. -->
<script setup lang="ts">
import UiIcon from './UiIcon.vue'

/** 折叠 Props：是否展开。Collapse props: expanded state. */
defineProps<{ modelValue?: boolean }>()
/** 事件：切换展开状态。Event: toggle expanded state. */
defineEmits<{ 'update:modelValue': [v: boolean] }>()
</script>

<style scoped>
.ui-disclosure { min-width: 0; }
/* 触发按钮：全宽左对齐，高度满足触达。Trigger: full-width, left-aligned, touch-target height. */
.ud-head {
  display: flex; align-items: center; gap: var(--sp-2);
  width: 100%; min-height: var(--min-target-size);
  padding: 0 var(--sp-2);
  background: none; border: none; cursor: pointer;
  color: var(--text-3); font-size: var(--fs-xs);
  font-family: inherit; text-align: left;
}
.ud-head:hover { color: var(--text-2); }
/* 末尾箭头贴右。Chevron pinned right. */
.ud-chev { margin-left: auto; flex-shrink: 0; }
.ud-chev.rot { transform: rotate(180deg); transition: transform var(--dur-base); }
@media (prefers-reduced-motion: reduce) { .ud-chev.rot { transition: none; } }
</style>
