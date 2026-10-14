<template>
  <section class="ui-card" :class="{ hover, padded: padded }" v-bind="$attrs">
    <!-- 带边框的标题行（`#header`）：起始页卡片原有一套 `.card-header`（标题 + 右侧徽章 +
        下边框），与这里的 mono 小标 `title` 是两种表达。收进 UiCard 后「卡片外壳」只剩一份
         实现（原先 UiCard 与 StartCard 各一套）。
         Bordered header row: the start page's cards used to carry their own `.card-header`
         (title + right-side badge + bottom border), a different expression from this mono caption.
         Moving it in leaves a single card-shell implementation. -->
    <div v-if="$slots.header" class="ui-card-head"><slot name="header" /></div>
    <span v-if="title || $slots.title" class="ui-card-title"><slot name="title">{{ title }}</slot></span>
    <slot />
  </section>
</template>

<!-- 卡片容器组件，支持标题、悬浮效果和内边距。Card container with optional title, hover effect, and padding. -->
<script setup lang="ts">
/** 卡片组件 Props：标题文本/是否启用悬浮交互/是否添加内边距。Card props: title text, hover interaction toggle, inner padding toggle. */
withDefaults(defineProps<{ title?: string; hover?: boolean; padded?: boolean }>(), { title: '', hover: false, padded: true })
</script>

<style scoped>
.ui-card {
  position: relative;
  border: 1px solid var(--glass-border);
  border-radius: var(--r-lg);
  background: var(--surface-card);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  box-shadow: var(--shadow-2);
}
.ui-card.padded { padding: var(--sp-4) var(--sp-q18); }
/* 标题行（`#header` 插槽）：左右分布 + 下边框，与起始页卡片原 `.card-header` 逐字一致。
   Header row (`#header` slot): space-between plus a bottom border, matching the start page's
   former `.card-header` verbatim. */
.ui-card-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--sp-4);
  border-bottom: 1px solid var(--glass-border);
}
/* 顶边发光线：品牌青 + 柔光（科技感批第一项）。原先是一道中性灰高光线。
   Glowing top edge: brand cyan plus a soft bloom. Was a neutral grey hairline. */
.ui-card::before {
  content: ''; position: absolute; top: 0; left: 14%; right: 14%; height: 1px;
  background: var(--hairline-brand); box-shadow: var(--glow-hairline); pointer-events: none;
}
.ui-card-title {
  display: block; margin-bottom: var(--sp-q10);
  font-family: var(--font-mono); font-size: var(--fs-2xs);
  letter-spacing: .16em; text-transform: uppercase; color: var(--text-3);
}
.ui-card.hover { transition: transform var(--dur-base) var(--ease-out), border-color var(--dur-base), box-shadow var(--dur-base); }
.ui-card.hover:hover { transform: translateY(-3px); border-color: rgba(103, 232, 249, .35); box-shadow: var(--shadow-3); }
</style>
