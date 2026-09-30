<template>
  <!-- 图标按钮：仅图标的操作键，title 兼作 tooltip 与无障碍名。
       Icon-only action button: title doubles as tooltip and accessible name. -->
  <button
    class="ui-icon-btn"
    :class="[`ib-${variant}`, { circle, compact }]"
    :data-compact="compact || undefined"
    :type="type"
    :disabled="disabled"
    :title="title"
    :aria-label="title"
    v-bind="$attrs"
  >
    <slot />
  </button>
</template>

<!-- 图标按钮组件：ghost（透明底 hover 灰底）/ brand（品牌渐变）两种变体；compact 用于密集行微操作（豁免全局 44px 触达下限）。Icon button: ghost / brand variants; compact for micro-actions in dense rows (exempts the global 44px target floor). -->
<script setup lang="ts">
/** 图标按钮 Props：提示文本/变体/圆形/紧凑/禁用/按钮类型。Icon button props: tooltip text, variant, circle, compact, disabled, button type. */
withDefaults(defineProps<{
  title?: string
  variant?: 'ghost' | 'brand'
  circle?: boolean
  compact?: boolean
  disabled?: boolean
  type?: 'button' | 'submit'
}>(), { title: '', variant: 'ghost', circle: false, compact: false, disabled: false, type: 'button' })
</script>

<style scoped>
.ui-icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  background: none; border: none;
  color: var(--text-2); cursor: pointer;
  padding: 6px; border-radius: var(--r-md);
  min-height: var(--min-target-size);
  min-width: var(--min-target-size);
  transition: color var(--dur-fast), background var(--dur-fast), opacity var(--dur-fast);
}
.ui-icon-btn:disabled { opacity: .4; cursor: not-allowed; }
.ib-ghost:hover:not(:disabled) { background: rgba(51, 65, 85, .55); color: var(--text-1); }
/* 紧凑：密集行微操作，豁免全局触达下限。Compact: micro-actions in dense rows, exempt from the global target floor. */
.ui-icon-btn.compact { min-height: auto; min-width: auto; padding: 3px; border-radius: var(--r-sm); }

/* 品牌变体：渐变圆钮（如聊天发送键）。Brand variant: gradient circle (e.g. chat send key). */
.ib-brand.circle {
  width: 34px; height: 34px; padding: 0;
  border-radius: 50%;
  background: var(--brand-grad); color: var(--text-on-brand);
  box-shadow: var(--glow-brand);
}
.ib-brand.circle:hover:not(:disabled) { filter: brightness(1.1); background: var(--brand-grad); }
</style>
