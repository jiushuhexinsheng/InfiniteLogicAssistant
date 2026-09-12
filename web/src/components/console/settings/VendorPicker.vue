<template>
  <!-- 厂商目录选择面板（新增 Profile）：从预设厂商快速创建配置。Vendor catalog panel (add Profile): quickly create config from vendor presets. -->
  <div class="cs-vendor">
    <p class="cs-vendor-tip">从厂商目录新增 Profile（自动预填端点/模型，可再手动调整）</p>
    <!-- 自定义名称内联输入（替代 window.prompt）。Custom name inline input (replaces window.prompt). -->
    <div v-if="s.customAdding.value === sectionKey" class="cs-vendor-custom">
      <UiInput v-model="s.customName.value" placeholder="Profile 名称（如 my-gateway）" @keyup.enter="s.confirmCustom(sectionKey)" />
      <UiButton variant="primary" size="sm" @click="s.confirmCustom(sectionKey)">创建</UiButton>
      <UiButton variant="secondary" size="sm" @click="s.customAdding.value = null">取消</UiButton>
    </div>
    <div v-else class="cs-vendor-grid">
      <button class="cs-vendor-chip custom" @click="s.customAdding.value = sectionKey">＋ 自定义（空白）</button>
      <button v-for="v in s.vendorList(sectionKey)" :key="v.id" class="cs-vendor-chip" @click="s.addProfileFromVendor(sectionKey, v)">
        {{ v.label }}
      </button>
    </div>
  </div>
</template>

<!-- 厂商目录面板：父组件传入所属模块 key。Vendor catalog panel: the parent passes the owning module key. -->
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
.cs-vendor-chip {
  font-size: var(--fs-2xs); font-family: var(--font-mono); color: var(--text-2);
  background: rgba(15, 23, 42, .6); border: 1px solid var(--border-soft);
  border-radius: var(--r-full); padding: 3px 10px; cursor: pointer;
}
.cs-vendor-chip:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.cs-vendor-chip.custom { border-style: dashed; color: var(--brand-c2); }
.cs-vendor-custom { display: flex; align-items: center; gap: 8px; }
.cs-vendor-custom :deep(.ui-input) { flex: 1; min-width: 0; }
</style>
