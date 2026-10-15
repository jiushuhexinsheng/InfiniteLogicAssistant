<template>
  <div
    class="console-pane"
    :style="{ '--pane-max': maxWidth ? maxWidth + 'px' : 'none', '--pane-gap': gap + 'px' }"
  ><slot /></div>
</template>

<!-- 控制台视图面板外壳：把「整页不滚、面板自滚」这套容器契约收在一处。
     Console view-pane shell: centralises the "page doesn't scroll, the pane does" container contract.

     原先 7 个 console 视图各自声明同一段容器 CSS：
     `.xxx { max-width: Npx; width: 100%; margin: 0 auto; flex: 1; min-height: 0; overflow-y: auto }`。
     抽出来的价值不只是少写几行 —— `flex:1 + min-height:0 + overflow-y:auto` 这组是「面板自滚」
     能成立的关键，散在 7 处时任何一处漏掉 min-height 都会让滚动行为悄悄变掉。

     The 7 console views each declared the same container CSS. The win isn't just fewer lines:
     the `flex:1 + min-height:0 + overflow-y:auto` trio is what makes "the pane scrolls, not the
     page" work — scattered across 7 files, one missing `min-height` silently breaks scrolling.

     **2026-10-15：`stack` 开关删掉了，面板一律是 flex 列。** 原先「不 stack 就保持块级流」是
     为了 ConsoleEnvView 的 `.env-pre`（带 max-height，flex 化会被压扁）。真正的病根不是 flex 本身，
     而是 flex 项默认 `flex-shrink: 1` —— 长内容会被压缩而**不是让面板滚动**。所以改成：面板一律
     flex 列，**会被压扁的子元素自己声明 `flex-shrink: 0`**（`.env-pre` 与 ConsoleTools 的
     `.tool-cards` 各一行）。这样空态才能用 `flex: 1` 长满并垂直居中（见 UiEmpty）。
     **`stack` was removed; the pane is always a flex column.** The old "block flow unless stacked"
     branch existed for ConsoleEnvView's `.env-pre` (a max-height element that flex would squash).
     The real culprit was never flex — it was the default `flex-shrink: 1` on flex items, which
     compresses long content instead of letting the pane scroll. Now the pane is always a flex
     column and the squishable children opt out with `flex-shrink: 0` (one line each in `.env-pre`
     and ConsoleTools' `.tool-cards`). That is what lets the empty state use `flex: 1` to fill and
     centre itself (see UiEmpty). -->
<script setup lang="ts">
/** 面板 Props：宽度上限与纵向间距。Pane props: max width and vertical gap. */
withDefaults(defineProps<{
  /** 内容区最大宽度（px）。不传则不设 max-width（对话区的消息列表用）。
   *  Max content width in px. Omit to leave max-width unset (the conversation message list). */
  maxWidth?: number
  /** 纵向间距（px），不传为 0。Vertical gap in px; 0 when omitted. */
  gap?: number
}>(), { maxWidth: 720, gap: 0 })
</script>

<style scoped>
.console-pane {
  width: 100%; margin: 0 auto;
  max-width: var(--pane-max);
  flex: 1; min-height: 0; overflow-y: auto;
  display: flex; flex-direction: column; gap: var(--pane-gap, 0);
}
</style>
