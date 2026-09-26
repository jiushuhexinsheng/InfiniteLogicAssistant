<template>
  <!-- 文件模块（占位）：协议预留 —— 显示文件名/路径/大小骨架卡。
       File block (placeholder): protocol reserved — renders a name/path/size skeleton. -->
  <div class="blk-file" :class="skin">
    <UiIcon name="file-text" :size="18" />
    <div class="f-meta">
      <div class="f-name">{{ block.payload.name || '文件' }}</div>
      <div class="f-path">{{ block.payload.path || '' }}</div>
    </div>
    <span v-if="block.payload.size != null" class="f-size">{{ sizeText }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { UiIcon } from '../ui'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 文件块。File block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 文件大小的人类可读文本。Human-readable file size. */
const sizeText = computed(() => {
  const n = Number(props.block.payload.size)
  if (!isFinite(n)) return ''
  return n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`
})
</script>

<style scoped>
.blk-file {
  display: flex; align-items: center; gap: var(--sp-2);
  border: 1px dashed var(--bg-3); border-radius: var(--r-md);
  padding: var(--sp-2) var(--sp-3); background: var(--bg-1); color: var(--text-3);
}
.f-meta { flex: 1; min-width: 0; }
.f-name { font-size: var(--fs-sm); color: var(--text-2); }
.f-path {
  font-size: var(--fs-xs); color: var(--text-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.f-size { font-size: var(--fs-xs); color: var(--text-3); }
</style>
