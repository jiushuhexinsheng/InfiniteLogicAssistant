<template>
  <!-- 回合汇总卡：头部（状态 + 摘要 + 计数徽章）+ 可折叠展开本轮回看。
       语音播报统一出口即 payload.tts_text（speechForBlocks 权威来源）。
       Turn summary card: header (status + summary + count badges) + collapsible
       turn review. The unified speech exit is payload.tts_text. -->
  <div class="blk-summary" :class="skin">
    <div class="s-head">
      <UiIcon :name="statusIcon" :size="13" />
      <span class="s-text">{{ block.payload.summary_text || '已完成' }}</span>
      <button class="s-toggle" :aria-expanded="open" @click="open = !open">
        <UiIcon name="chevron-down" :size="11" :class="{ rot: open }" />
      </button>
    </div>
    <div class="s-counts">
      <span v-for="(n, t) in (block.payload.counts || {})" :key="t" class="s-chip">
        {{ t }} × {{ n }}
      </span>
    </div>
    <div v-if="open" class="s-review">
      <!-- 本轮回看：按 block_ids 过滤同级块，递归交给 BlockHost 渲染（不含自身）。
           Turn review: sibling blocks filtered by block_ids, rendered recursively
           via BlockHost (excluding the summary itself). -->
      <BlockHost v-if="reviewBlocks.length" :blocks="reviewBlocks" :skin="skin" />
      <div v-else class="s-review-hint">（本轮回看为空）</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { UiIcon } from '../ui'
import BlockHost from './BlockHost.vue'
import { BLOCKS_CONTEXT } from '../../blocks/context'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 汇总块。Summary block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 是否展开本轮回看。Whether the turn review is expanded. */
const open = ref(false)

/** 同级块列表获取器（BlockHost provide；无宿主时退化为空列表）。
 *  Sibling block getter (provided by BlockHost; degrades to an empty list). */
const getSiblingBlocks = inject(BLOCKS_CONTEXT, () => [] as Block[])

/** 本轮回看块：按 payload.block_ids 过滤同级块，排除汇总块自身。
 *  Turn review blocks: siblings filtered by payload.block_ids, excluding the summary. */
const reviewBlocks = computed(() => {
  const ids: string[] = props.block.payload.block_ids || []
  if (!ids.length) return []
  const idSet = new Set(ids)
  return getSiblingBlocks().filter((b: Block) => idSet.has(b.id) && b.id !== props.block.id)
})

/** 状态图标。Status icon. */
const statusIcon = computed(() => {
  const s = props.block.payload.status
  return s === 'failed' ? 'alert' : s === 'stopped' || s === 'cancelled' ? 'stop' : 'check'
})
</script>

<style scoped>
.blk-summary {
  border: 1px solid var(--bg-3); border-radius: var(--r-md);
  background: var(--bg-1); padding: var(--sp-2) var(--sp-3);
}
.s-head { display: flex; align-items: center; gap: var(--sp-2); }
.s-text { flex: 1; font-size: var(--fs-sm); color: var(--text-1); }
.s-toggle {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  background: none; border: none; cursor: pointer; color: var(--text-3);
}
.s-counts { display: flex; flex-wrap: wrap; gap: var(--sp-1); margin-top: var(--sp-1); }
.s-chip {
  font-size: var(--fs-xs); color: var(--text-3);
  border: 1px solid var(--bg-3); border-radius: var(--r-sm); padding: 1px 6px;
}
.s-review { margin-top: var(--sp-2); border-top: 1px solid var(--bg-2); padding-top: var(--sp-2); }
.s-review-hint { font-size: var(--fs-xs); color: var(--text-3); }
.rot { transform: rotate(180deg); transition: transform .2s; }
@media (prefers-reduced-motion: reduce) { .rot { transition: none; } }
</style>
