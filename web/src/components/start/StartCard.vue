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
/* 科技感批：起始页卡片迁到**玻璃语言** —— 与控制台同款（半透明底 + 模糊 + 品牌青描边 +
   顶部发光线）。原先是实心 `--bg-1` + 中性描边 + `--r-xl` 且无模糊/无发光线；控制台的卡片
   全都发光之后，两种语言的落差比「有意共存」时大得多，起点页看着像另一个产品。
   Glass language for the start page: translucent fill + blur + brand-cyan border + the glowing top
   hairline, i.e. the same as the console. It used to be opaque --bg-1 with a neutral border and no
   hairline; once the console cards all glow, the gap between the two languages reads as "a
   different product" rather than "two coexisting card styles". */
.card {
  position: relative;
  flex: 1 1 400px;
  max-width: 480px;
  background: var(--surface-card);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-2);
  overflow: hidden;
}
.card::before {
  content: ''; position: absolute; top: 0; left: 14%; right: 14%; height: 1px;
  background: var(--hairline-brand); box-shadow: var(--glow-hairline); pointer-events: none;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  /* 与新的玻璃描边同色 —— 漏了它，卡头分隔线会是这一页唯一的灰色线。
     Same colour as the new glass border; leaving it grey would make this the only grey line here. */
  border-bottom: 1px solid var(--glass-border);
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
