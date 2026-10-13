<template>
  <!-- 图片模块（占位）：协议预留，采集通道本轮未接入 —— 显示 src/alt 骨架卡。
       Image block (placeholder): protocol reserved, capture channel not wired this
       round — renders a src/alt skeleton card. -->
  <UiHint class="blk-image" :class="skin">
    <UiIcon name="image" :size="18" />
    <div class="i-meta">
      <div class="i-alt">{{ block.payload.alt || '图片' }}</div>
      <div class="i-src">{{ block.payload.src || '（未接入采集通道）' }}</div>
    </div>
  </UiHint>
</template>

<script setup lang="ts">
import { UiHint, UiIcon } from '../ui'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 图片块。Image block.
 * @property skin - 渲染皮肤。Render skin.
 */
defineProps<{ block: Block; skin?: Skin }>()
</script>

<style scoped>
/* 虚线框与底色由 UiHint 提供。Dashed border and fill come from UiHint. */
.blk-image {
  display: flex; align-items: center; gap: var(--sp-2);
  padding: var(--sp-3); color: var(--text-3);
}
.i-meta { min-width: 0; }
.i-alt { font-size: var(--fs-sm); color: var(--text-2); }
.i-src {
  font-size: var(--fs-xs); color: var(--text-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
