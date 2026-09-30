<template>
  <!-- 折叠头：全宽触发按钮（aria-expanded）+ 旋转箭头 + 展开内容。
       Disclosure: full-width trigger (aria-expanded) + rotating chevron + expanded content. -->
  <div class="ui-disclosure">
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
