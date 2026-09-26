<template>
  <!-- 正文模块：bubble 气泡排版（换行折叠）/ doc 文档排版（保留换行全宽）。
       Text block: bubble layout (folded newlines) / doc layout (kept newlines, full width). -->
  <div class="blk-text" :class="[skin, variant]">
    <MarkdownRenderer :text="md" :preserve-newlines="variant === 'doc'" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownRenderer from '../MarkdownRenderer.vue'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 正文块。Text block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 正文 markdown。Body markdown. */
const md = computed(() => String(props.block.payload.md || ''))

/** 排版变体（bubble 气泡 / doc 文档）。Layout variant. */
const variant = computed(() => props.block.payload.variant === 'doc' ? 'doc' : 'bubble')
</script>

<style scoped>
.blk-text.doc { white-space: pre-wrap; max-width: none; }
.blk-text.doc :deep(.md) { white-space: pre-wrap; }
</style>
