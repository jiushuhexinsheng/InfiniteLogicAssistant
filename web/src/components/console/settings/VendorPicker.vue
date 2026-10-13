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
.cs-vendor {
  border: 1px dashed var(--border-soft); border-radius: var(--r-sm);
  padding: 8px 10px; background: rgba(15, 23, 42, .4);
}
.cs-vendor-tip { font-size: var(--fs-2xs); color: var(--text-3); margin: 0 0 7px; }
.cs-vendor-grid { display: flex; flex-wrap: wrap; gap: 6px; }
/* 覆盖 UiButton 的 .ui-btn.s-sm（双类 + 容器层级保特异性胜出），保持紧凑 mono chip 观感。
   Overrides UiButton's .ui-btn.s-sm (container + double class keeps specificity ahead) for the compact mono chip look. */
.cs-vendor .cs-vendor-grid .cs-vendor-chip {
  font-size: var(--fs-2xs); font-family: var(--font-mono); color: var(--text-2);
  background: rgba(15, 23, 42, .6); border: 1px solid var(--border-soft);
  border-radius: var(--r-full); padding: 3px 10px;
}
.cs-vendor .cs-vendor-grid .cs-vendor-chip:hover { color: var(--brand-c2); border-color: var(--brand-c2); background: rgba(15, 23, 42, .6); }
.cs-vendor .cs-vendor-grid .cs-vendor-chip.custom { border-style: dashed; color: var(--brand-c2); }
.cs-vendor-custom { display: flex; align-items: center; gap: var(--sp-2); }
.cs-vendor-custom :deep(.ui-input) { flex: 1; min-width: 0; }
</style>
