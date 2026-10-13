<template>
  <div class="card">
    <div class="card-header">
      <span class="card-title"><slot name="title">{{ title }}</slot></span>
      <slot name="badge" />
    </div>
    <div class="card-body"><slot /></div>
  </div>
</template>

<!-- 起始页卡片外壳：实心卡（非玻璃卡）。Start-page card shell: a solid card (not the glass one).

     注意它**不**复用 `ui/UiCard`：起始页的 `.card` 是 `--bg-1` 不透明 + `--r-xl`(16px) + 无
     backdrop-filter/hairline，而 `UiCard` 是 `--surface-card` 玻璃 + `--r-lg`(12px) + 模糊 + 顶部
     高光线 —— 两者是有意共存的两套卡片语言，替换属于视觉批，不属于本次结构搬迁。
     Note it does **not** reuse `ui/UiCard`: this `.card` is opaque `--bg-1` + `--r-xl` (16px) with
     no backdrop-filter/hairline, while `UiCard` is glassy `--surface-card` + `--r-lg` (12px) +
     blur + top hairline. The two card languages coexist on purpose; swapping them is visual-batch
     work, not this structural move. -->
<script setup lang="ts">
/** 卡头标题。Title for the card head. */
withDefaults(defineProps<{ title?: string }>(), { title: '' })
</script>

<style scoped>
.card {
  flex: 1 1 400px;
  max-width: 480px;
  background: var(--bg-1);
  border: 1px solid var(--border-base);
  border-radius: var(--r-xl);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  border-bottom: 1px solid var(--border-base);
}

.card-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-1);
}

.card-body {
  padding: var(--sp-4);
}
/* 网格与刷新按钮的间距（按钮已是 UiButton，间距由容器补）。Gap between grid and refresh button (button is UiButton; spacing comes from the container).
   仍在 slot 内容上生效，所以 `:deep()` 不能去掉 —— 这些按钮属于调用方的作用域。
   Still applies to slot content, so `:deep()` cannot be dropped — those buttons belong to the
   caller's scope. */
.card-body :deep(.ui-btn) { margin-top: var(--sp-3); }
</style>
