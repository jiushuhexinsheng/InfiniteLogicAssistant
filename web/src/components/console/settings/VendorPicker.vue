<template>
  <!-- 新增 Profile 面板：内联输入名称 → 创建空白 profile（唯一新增路径；厂商目录已退役）。
       Add-profile panel: inline name input → create a blank profile (the only way to add;
       the vendor catalogue retired 2026-10-11). -->
  <div class="cs-vendor">
    <p class="cs-vendor-tip">新增 Profile（自填 endpoint / 模型 / 密钥，可保存多个随时切换）</p>
    <!-- 自定义名称内联输入（替代 window.prompt）。Custom name inline input (replaces window.prompt). -->
    <div v-if="s.customAdding.value === sectionKey" class="cs-vendor-custom">
      <UiInput v-model="s.customName.value" placeholder="Profile 名称（如 my-gateway）" @keyup.enter="s.confirmCustom(sectionKey)" />
      <UiButton variant="primary" size="sm" @click="s.confirmCustom(sectionKey)">创建</UiButton>
      <UiButton variant="secondary" size="sm" @click="s.customAdding.value = null">取消</UiButton>
    </div>
    <div v-else class="cs-vendor-grid">
      <UiButton size="sm" shape="pill" class="cs-vendor-chip custom" @click="s.customAdding.value = sectionKey">＋ 新增模型</UiButton>
    </div>
  </div>
</template>

<!-- 新增面板：父组件传入所属模块 key。Add panel: the parent passes the owning module key. -->
<script setup lang="ts">
import { UiButton, UiInput } from '../../ui'
import { useSettings } from './useSettings'

/** 组件 props：所属模块 key。Component props: the owning module key. */
const props = defineProps<{ sectionKey: string }>()

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/** 所属模块 key。The owning module key. */
const sectionKey = props.sectionKey
</script>

<style scoped>
/* ⚠️ 这圈虚线**不并进 UiHint**（10.3 实测 + 本轮判定）。UiHint 框的是**非文本块的占位**
   （思考/文件/图片/未知），那四值（--bg-3 / --r-md / --bg-1）是那类块的统一语言；这里框的是
   **承载交互内容的内联面板**（名称输入 + 新增 chip），描边更弱（--border-soft）、圆角更小
   （--r-sm）、底色更深且半透明（rgba(15,23,42,.4)）—— 四项全不同是两种用途，不是疏漏。
   要强行合并，要么给 UiHint 加四个 prop（变配置袋），要么改这里的观感，两条都不划算。
   ⚠️ This dashed ring does **not** fold into UiHint. UiHint frames non-text *placeholders*
   (thinking/file/image/unknown) and its four values are that family's shared language; this one
   wraps an *interactive inline panel* (name input + add chip) with a fainter border, smaller
   radius and a darker translucent fill. All four differ on purpose — two different jobs, not an
   oversight. Merging would either turn UiHint into a four-prop bag or change this panel's look. */
.cs-vendor {
  border: 1px dashed var(--border-soft); border-radius: var(--r-sm);
  padding: var(--sp-2) var(--sp-q10); background: rgba(15, 23, 42, .4);
}
.cs-vendor-tip { font-size: var(--fs-2xs); color: var(--text-3); margin: 0 0 var(--sp-2); }
.cs-vendor-grid { display: flex; flex-wrap: wrap; gap: var(--sp-q6); }
/* 覆盖 UiButton 的 .ui-btn.s-sm（双类 + 容器层级保特异性胜出），保持紧凑 mono chip 观感。
   Overrides UiButton's .ui-btn.s-sm (container + double class keeps specificity ahead) for the compact mono chip look. */
.cs-vendor .cs-vendor-grid .cs-vendor-chip {
  font-size: var(--fs-2xs); font-family: var(--font-mono); color: var(--text-2);
  background: rgba(15, 23, 42, .6); border: 1px solid var(--border-soft);
  border-radius: var(--r-full); padding: var(--sp-1) var(--sp-q10);
}
.cs-vendor .cs-vendor-grid .cs-vendor-chip:hover { color: var(--brand-c2); border-color: var(--brand-c2); background: rgba(15, 23, 42, .6); }
.cs-vendor .cs-vendor-grid .cs-vendor-chip.custom { border-style: dashed; color: var(--brand-c2); }
.cs-vendor-custom { display: flex; align-items: center; gap: var(--sp-2); }
.cs-vendor-custom :deep(.ui-input) { flex: 1; min-width: 0; }
</style>
