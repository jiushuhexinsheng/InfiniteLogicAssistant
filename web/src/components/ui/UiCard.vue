<template>
  <section class="ui-card" :class="{ hover, padded: padded }" v-bind="$attrs">
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
.ui-card.padded { padding: 16px 18px; }
.ui-card::before {
  content: ''; position: absolute; top: 0; left: 14%; right: 14%; height: 1px;
  background: var(--hairline); pointer-events: none;
}
.ui-card-title {
  display: block; margin-bottom: 10px;
  font-family: var(--font-mono); font-size: var(--fs-2xs);
  letter-spacing: .16em; text-transform: uppercase; color: var(--text-3);
}
.ui-card.hover { transition: transform var(--dur-base) var(--ease-out), border-color var(--dur-base), box-shadow var(--dur-base); }
.ui-card.hover:hover { transform: translateY(-3px); border-color: rgba(103, 232, 249, .35); box-shadow: var(--shadow-3); }
</style>
