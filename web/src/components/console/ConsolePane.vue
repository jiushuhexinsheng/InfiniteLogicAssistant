<template>
  <div
    class="console-pane"
    :class="{ stacked: stack }"
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
     page" work — scattered across 7 files, one missing `min-height` silently breaks scrolling. -->
<script setup lang="ts">
/** 面板 Props：宽度上限与是否纵向分栏。Pane props: max width and whether to stack vertically. */
withDefaults(defineProps<{
  /** 内容区最大宽度（px）。不传则不设 max-width（对话区的消息列表用）。
   *  Max content width in px. Omit to leave max-width unset (the conversation message list). */
  maxWidth?: number
  /** 纵向排列 + 间距。⚠️ 为 false 时保持**块级**流（不是 flex）——ConsoleEnvView 的
   *  `.env-pre` 带 max-height，若被 flex 化会被压缩，外观就变了。
   *  Stack vertically with a gap. ⚠️ When false the pane stays **block** flow, NOT flex —
   *  ConsoleEnvView's `.env-pre` carries a max-height that flex would shrink, changing the look. */
  stack?: boolean
  /** 纵向间距（px），仅 stack 时生效。Vertical gap in px; only meaningful when stacked. */
  gap?: number
}>(), { maxWidth: 720, stack: false, gap: 0 })
</script>

<style scoped>
.console-pane {
  width: 100%; margin: 0 auto;
  max-width: var(--pane-max);
  flex: 1; min-height: 0; overflow-y: auto;
}
.console-pane.stacked { display: flex; flex-direction: column; gap: var(--pane-gap, 0); }
</style>
