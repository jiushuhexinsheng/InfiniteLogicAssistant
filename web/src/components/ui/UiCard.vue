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
/* 上缘品牌微光（科技感）：卡片内侧一层自上而下淡出的青绿，读作「被从上方照亮」的层次。
   为什么用伪元素而不是改描边：`tokens.css` 明确裁定过「玻璃描边共用一个值、不给 UiCard 加私有
   描边」，那正是 `--glass-border` 偏青是一处编辑的原因 —— 本项不碰它，只往**内侧**加光。
   `z-index: -1` 是关键：`.ui-card` 带 `backdrop-filter`，**本身即堆叠上下文**，所以负 z 的伪元素
   落在「卡片底色之上、内容之下」，不会把标题和正文蒙上一层。（若哪天 backdrop-filter 被去掉，
   它会掉到卡片底**下面**、整个效果消失 —— 那时改用 `::before` + z-index:1 即可。）
   Top-edge brand sheen: a cyan wash fading downward inside the card, reading as "lit from above".
   A pseudo-element rather than a border change on purpose — tokens.css explicitly ruled that the
   glass border is one shared value and UiCard gets no private border (that is why "the glass leans
   cyan" is a single edit). This adds light to the **inside** instead. `z-index: -1` matters: the
   card carries `backdrop-filter`, so it is a stacking context, and a negative-z pseudo lands above
   the card fill but below its content — it must not wash over the title and body. (If
   backdrop-filter is ever dropped the sheen falls behind the fill and disappears; switch to
   `::before` + z-index:1 then.) */
.ui-card::after {
  content: ''; position: absolute; inset: 0; border-radius: inherit; z-index: -1;
  /* 渐变的**长度按卡片高度算比例**，所以短卡（起始页那四块特性卡）会显得比长卡重 ——
     36% 是照着「一条顶部光带」调的：短卡上占顶部小半，长卡上只够到标题行下方。
     The gradient is a **percentage of the card height**, so short cards (the start page's four
     feature cards) read heavier than tall ones. 36% is tuned for "a light band across the top":
     a small upper slice on short cards, just past the title row on tall ones. */
  background: linear-gradient(180deg, rgba(103, 232, 249, .12), transparent 36%);
  pointer-events: none;
}
.ui-card-title {
  display: block; margin-bottom: var(--sp-q10);
  font-family: var(--font-mono); font-size: var(--fs-2xs);
  letter-spacing: .16em; text-transform: uppercase; color: var(--text-3);
}
.ui-card.hover { transition: transform var(--dur-base) var(--ease-out), border-color var(--dur-base), box-shadow var(--dur-base); }
.ui-card.hover:hover { transform: translateY(-3px); border-color: rgba(103, 232, 249, .35); box-shadow: var(--shadow-3); }
</style>
