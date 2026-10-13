<template>
  <div class="ui-empty" :class="`pad-${pad}`"><slot>{{ text }}</slot></div>
</template>

<!-- 空态 / 加载占位。Empty-state / loading placeholder.
     收编原先散在 6 个 console 视图里逐字重复的 `.console-empty`。
     Collects the `.console-empty` blocks that were duplicated verbatim across 6 console views. -->
<script setup lang="ts">
/** 空态 Props：文案与纵向内边距档位。Empty-state props: text and vertical padding tier. */
withDefaults(defineProps<{
  /** 占位文案（复杂节点走默认 slot）。Placeholder text (use the default slot for richer nodes). */
  text?: string
  /** 纵向内边距：md=40px（多数视图），sm=30px（ConsoleHistory 的既有值，勿改成 md——那会改外观）。
   *  Vertical padding: md=40px (most views), sm=30px (ConsoleHistory's existing value — don't
   *  normalise it to md, that would change the look). */
  pad?: 'sm' | 'md'
}>(), { text: '', pad: 'md' })
</script>

<style scoped>
/* `text-align: center` 对单行文案是 no-op（flex 项宽度=文本宽度），只在长文案换行时生效
   —— ConsoleLibrary 原本就带它。统一带上不改变任何现有视图。
   `text-align: center` is a no-op for a single-line label (the flex item is exactly as wide as
   the text) and only matters once the text wraps — ConsoleLibrary already had it. Carrying it
   universally changes nothing in any current view. */
.ui-empty {
  display: flex; justify-content: center; text-align: center;
  color: var(--text-3); font-size: 13px;
}
.ui-empty.pad-md { padding: var(--sp-q40) 0; }
.ui-empty.pad-sm { padding: var(--sp-q30) 0; }
</style>
