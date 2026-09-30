<template>
  <button
    class="ui-btn"
    :class="[`v-${variant}`, `s-${size}`, `h-${hover}`, `sh-${shape}`, { block, loading }]"
    :disabled="disabled || loading"
    :type="type"
    v-bind="$attrs"
  >
    <span v-if="loading" class="ui-btn-spinner" aria-hidden="true"></span>
    <slot />
  </button>
</template>

<!-- 通用按钮组件，支持多种变体、尺寸、形状和加载状态。General-purpose button with variant, size, shape, and loading state support. -->
<script setup lang="ts">
/** 按钮组件 Props：变体/尺寸/形状（胶囊/方角）/悬浮样式/是否占满行宽/加载态/禁用态/按钮类型。Button component props: variant, size, shape (pill/square), hover style, full-width, loading, disabled, button type. */
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  shape?: 'pill' | 'square'
  hover?: 'brand' | 'danger'
  block?: boolean
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit'
}>(), { variant: 'primary', size: 'md', shape: 'pill', hover: 'brand', block: false, loading: false, disabled: false, type: 'button' })
</script>

<style scoped>
.ui-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  font-family: inherit; font-weight: 500; line-height: 1;
  border: 1px solid transparent; border-radius: 999px; cursor: pointer;
  white-space: nowrap; user-select: none;
  min-height: var(--min-target-size); /* 确保最小点击目标 */
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-base) var(--ease-out),
    background var(--dur-base), border-color var(--dur-base), color var(--dur-base), opacity var(--dur-fast);
}
/* 形状：胶囊（默认）/ 方角（选项按钮等）。Shape: pill (default) / square (option buttons etc.). */
.sh-square { border-radius: var(--r-md); }
.ui-btn:active:not(:disabled) { transform: translateY(0) scale(.97); }
.ui-btn:disabled { opacity: .5; cursor: not-allowed; }
.h-danger:hover:not(:disabled) { color: var(--err); border-color: var(--err); }

.s-sm { padding: 8px 16px; font-size: var(--fs-xs); }
.s-md { padding: 10px 22px; font-size: var(--fs-md); }
.s-lg { padding: 12px 28px; font-size: var(--fs-lg); }

/* 主要按钮：渐变底 + 悬浮上浮 2px + 阴影加深。
   Primary: gradient base + 2px lift on hover + deeper shadow. */
.v-primary {
  background: var(--brand-grad);
  background-size: 140% 140%;
  color: var(--text-on-brand);
  font-weight: 600;
  box-shadow: var(--glow-brand);
}
.v-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: var(--glow-brand), var(--shadow-2);
  background-position: 60% 50%;
}

.v-secondary { background: var(--glass-bg); color: var(--text-1); border-color: var(--glass-border); backdrop-filter: blur(10px); }
.v-secondary:hover:not(:disabled) { border-color: var(--brand-c2); color: var(--brand-c2); background: var(--surface-control-hover); transform: translateY(-1px); box-shadow: var(--shadow-1); }
.v-ghost { background: none; color: var(--text-2); }
.v-ghost:hover:not(:disabled) { color: var(--brand-c2); background: rgba(103, 232, 249, .08); }
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
