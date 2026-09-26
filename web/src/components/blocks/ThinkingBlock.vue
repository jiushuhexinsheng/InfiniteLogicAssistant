<template>
  <!-- 思考模块：默认折叠（meta.collapsed），点击展开；默认不播报（meta.tts=skip）。
       Thinking block: collapsed by default, click to expand; silent by default. -->
  <div class="blk-thinking" :class="skin">
    <button class="th-head" :aria-expanded="open" @click="open = !open">
      <UiIcon name="brain" :size="12" />
      <span class="th-label">思考过程</span>
      <UiIcon name="chevron-down" :size="11" :class="{ rot: open }" />
    </button>
    <div v-if="open" class="th-body">{{ block.payload.text }}</div>
    <div v-else class="th-preview">{{ preview }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { UiIcon } from '../ui'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 思考块。Thinking block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 是否展开（缺省取 meta.collapsed 取反）。Whether expanded. */
const open = ref(!props.block.meta?.collapsed)

/** 折叠态预览：首行截 60 字。Collapsed preview: first line truncated to 60 chars. */
const preview = computed(() => {
  const t = String(props.block.payload.text || '')
  return t.length > 60 ? t.slice(0, 60) + '…' : t
})
</script>

<style scoped>
.blk-thinking {
  border: 1px dashed var(--bg-3); border-radius: var(--r-md);
  background: var(--bg-1); padding: var(--sp-2);
}
.th-head {
  display: flex; align-items: center; gap: var(--sp-2);
  width: 100%; min-height: var(--min-target-size, 44px);
  background: none; border: none; cursor: pointer;
  color: var(--text-3); font-size: var(--fs-xs);
}
.th-label { flex: 1; text-align: left; }
.th-body {
  margin-top: var(--sp-2); white-space: pre-wrap;
  color: var(--text-2); font-size: var(--fs-sm); line-height: 1.5;
}
.th-preview {
  margin-top: var(--sp-1); color: var(--text-3);
  font-size: var(--fs-xs); opacity: .8;
}
.rot { transform: rotate(180deg); transition: transform .2s; }
@media (prefers-reduced-motion: reduce) { .rot { transition: none; } }
</style>
