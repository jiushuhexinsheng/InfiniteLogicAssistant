<template>
  <button
    class="ui-btn"
    :class="[`v-${variant}`, `s-${size}`, `h-${hover}`, { block, loading }]"
    :disabled="disabled || loading"
    :type="type"
    v-bind="$attrs"
  >
    <span v-if="loading" class="ui-btn-spinner" aria-hidden="true"></span>
    <slot />
  </button>
</template>

<!-- 通用按钮组件，支持多种变体、尺寸和加载状态。General-purpose button with variant, size, and loading state support. -->
<script setup lang="ts">
/** 按钮组件 Props：变体/尺寸/悬浮样式/是否占满行宽/加载态/禁用态/按钮类型。Button component props: variant, size, hover style, full-width, loading, disabled, button type. */
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  hover?: 'brand' | 'danger'
  block?: boolean
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit'
}>(), { variant: 'primary', size: 'md', hover: 'brand', block: false, loading: false, disabled: false, type: 'button' })
</script>

<style scoped>
.ui-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  font-family: inherit; font-weight: 500; line-height: 1;
  border: 1px solid transparent; border-radius: 999px; cursor: pointer;
  white-space: nowrap; user-select: none;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-base) var(--ease-out),
    background var(--dur-base), border-color var(--dur-base), color var(--dur-base), opacity var(--dur-fast);
}
.ui-btn:active:not(:disabled) { transform: translateY(0) scale(.97); }
.ui-btn:disabled { opacity: .5; cursor: not-allowed; }
.h-danger:hover:not(:disabled) { color: var(--err); border-color: var(--err); }

.s-sm { padding: 5px 14px; font-size: var(--fs-xs); }
.s-md { padding: 10px 22px; font-size: var(--fs-md); }
.s-lg { padding: 12px 28px; font-size: var(--fs-lg); }

.v-primary { background: var(--brand-grad); color: var(--text-on-brand); font-weight: 600; box-shadow: var(--glow-brand); }
.v-primary:hover:not(:disabled) { transform: translateY(-1px); }
.v-secondary { background: var(--glass-bg); color: var(--text-1); border-color: var(--glass-border); backdrop-filter: blur(10px); }
.v-secondary:hover:not(:disabled) { border-color: var(--brand-c2); color: var(--brand-c2); background: var(--surface-control-hover); }
.v-ghost { background: none; color: var(--text-2); }
.v-ghost:hover:not(:disabled) { color: var(--brand-c2); }
.v-danger { background: none; color: var(--text-2); border-color: var(--border-soft); font-size: var(--fs-xs); font-family: var(--font-mono); }
.v-danger:hover:not(:disabled) { color: var(--err); border-color: var(--err); }

.ui-btn.block { width: 100%; }
.ui-btn.loading { cursor: wait; }
.ui-btn-spinner {
  width: 12px; height: 12px; border-radius: 50%;
  border: 2px solid currentColor; border-top-color: transparent;
  animation: ui-spin .7s linear infinite;
}
@keyframes ui-spin { to { transform: rotate(360deg); } }
</style>
