<template>
  <div class="ui-empty"><slot>{{ text }}</slot></div>
</template>

<!-- 空态 / 加载占位。Empty-state / loading placeholder.
     收编原先散在 6 个 console 视图里逐字重复的 `.console-empty`。
     Collects the `.console-empty` blocks that were duplicated verbatim across 6 console views. -->
<script setup lang="ts">
/** 空态 Props：占位文案。Empty-state props: the placeholder text. */
withDefaults(defineProps<{
  /** 占位文案（复杂节点走默认 slot）。Placeholder text (use the default slot for richer nodes). */
  text?: string
}>(), { text: '' })
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
  /* 纵向内边距统一到 40px（科技感批 10.5）。本轮之前是 md=40 / sm=30 两档，而 30px 只有
     ConsoleHistory 一个消费者 —— 结构批把「不统一 padding」写进了注释（那是对的，结构批
     不动外观），视觉批来收它。40px 是 5/6 的既有值，所以动的只有 history 一张空态图。
     Vertical padding unified to 40px. Previously two tiers, md=40 / sm=30, with 30px having a
     single consumer (ConsoleHistory). The structural batch deliberately kept the split (right:
     it did not touch looks); the visual batch collects it. 40px is the existing value in 5 of 6
     views, so only the history empty-state shot moves. */
  padding: var(--sp-q40) 0;
}
</style>
