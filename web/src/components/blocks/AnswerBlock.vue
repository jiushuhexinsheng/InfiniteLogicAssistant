<template>
  <!-- 操作员作答模块：作答文本 + 来源徽章（typed/voice/button，语音可审计）。
       Operator answer block: answer text + source badge (voice answers auditable). -->
  <div class="blk-answer" :class="skin">
    <span class="a-text">{{ block.payload.text || (block.payload.choice ? block.payload.choice : '（空）') }}</span>
    <span v-if="block.payload.source" class="a-source">{{ sourceLabel }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 作答块。Answer block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 来源徽章文案。Source badge label. */
const sourceLabel = computed(() => {
  const s = props.block.payload.source
  return s === 'voice' ? '语音' : s === 'button' ? '按钮' : '输入'
})
</script>

<style scoped>
.blk-answer {
  display: flex; align-items: center; gap: var(--sp-2);
  padding: var(--sp-1) var(--sp-2); border-radius: var(--r-md);
  background: var(--bg-2); font-size: var(--fs-sm); color: var(--text-2);
}
.a-text { flex: 1; }
.a-source {
  font-size: var(--fs-xs); color: var(--text-3);
  border: 1px solid var(--bg-3); border-radius: var(--r-sm); padding: 1px 6px;
}
</style>
