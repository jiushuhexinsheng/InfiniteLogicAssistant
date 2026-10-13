<template>
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title"><slot name="title">{{ title }}</slot></span>
      <slot name="actions" />
    </div>
    <!-- 卡体：唯一滚动面（卡头固定在其上方）。The card body: the only scrolling surface
         (the card head stays fixed above it). -->
    <div class="cs-card-body"><slot /></div>
  </UiCard>
</template>

<!-- 设置卡片外壳：卡头（标题 + 右侧动作）固定，卡体自滚。
     Settings card shell: fixed head (title + right-side actions), self-scrolling body.

     抽取前，`.cs-card*` 的样式被定义了两处 —— 布局部分在 ConsoleSettings 的 `:deep()` 里反向
     穿透进子组件，外观部分在 6 张卡各自的 scoped 样式里各写一遍。两处合并到这里，父组件那段
     `:deep()` 随之删除。
     Before extraction the `.cs-card*` styles lived in two places: the layout half in
     ConsoleSettings' `:deep()` reaching into the children, the appearance half written out in
     each of the 6 cards' scoped styles. Both are merged here, and the parent's `:deep()` block
     is gone. -->
<script setup lang="ts">
import { UiCard } from '../../ui'

/** 卡片标题。标题内容复杂时可用 `#title` slot 覆盖。Card title; use the `#title` slot for richer content. */
withDefaults(defineProps<{ title?: string }>(), { title: '' })
</script>

<style scoped>
/* 以下四条合并自 ConsoleSettings 的 :deep() 块（2026-10-11 第三轮裁定）与 6 张卡各自的 scoped
   定义。**布局语义不可简化**：整页不滚动 —— 标题/菜单/卡头固定，只有卡体（保存行以下）自己滚，
   滚动轴正好落在「保存」正下方。
   The four rules below merge ConsoleSettings' `:deep()` block (2026-10-11 third-round ruling)
   with the 6 cards' own scoped definitions. **The layout semantics are not to be simplified**:
   the page never scrolls — title, menu and card heads stay fixed and only each card body
   (below the save row) scrolls, placing the scrollbar right under 保存. */
.cs-card {
  display: flex; flex-direction: column; gap: 12px;
  /* 内容超出可用高度时收缩（不撑破内容区）；短卡保持自然高度。
     Shrink when content exceeds the available height (never bursting the region); short cards
     keep their natural height. */
  flex: 0 1 auto; min-height: 0; overflow: hidden;
}
/* 卡头永不收缩。The card head never shrinks. */
.cs-card-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  flex-shrink: 0;
}
.cs-card-title { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); letter-spacing: .02em; }
.cs-card-body {
  flex: 1 1 auto; min-height: 0; overflow-y: auto;
  display: flex; flex-direction: column; gap: 12px;
  padding-right: 4px;
}
</style>
