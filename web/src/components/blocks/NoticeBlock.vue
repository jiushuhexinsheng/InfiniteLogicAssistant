<template>
  <!-- 系统提示模块：info/warn/error 三级（notify 提示、错误、状态行）。
       Notice block: info/warn/error levels (notify hints, errors, status lines). -->
  <div class="blk-notice" :class="[skin, level]">{{ block.payload.text }}</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 提示块。Notice block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 提示级别（缺省 info）。Notice level (defaults to info). */
const level = computed(() => props.block.payload.level || 'info')
</script>

<style scoped>
.blk-notice {
  padding: var(--sp-1) var(--sp-3); border-radius: var(--r-md);
  font-size: var(--fs-xs); text-align: center; color: var(--text-3);
  background: var(--bg-1);
}
.blk-notice.warn { color: var(--warn, #fbbf24); background: rgba(251, 191, 36, .08); }
.blk-notice.error { color: var(--err, #fca5a5); background: rgba(127, 29, 29, .35); }
</style>
