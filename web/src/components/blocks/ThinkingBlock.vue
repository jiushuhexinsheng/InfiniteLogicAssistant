<template>
  <!-- 思考模块：默认折叠（meta.collapsed），点击展开；默认不播报（meta.tts=skip）。
       Thinking block: collapsed by default, click to expand; silent by default. -->
  <div class="blk-thinking" :class="skin">
    <UiDisclosure v-model="open">
      <template #head>
        <UiIcon name="brain" :size="12" />
        <span class="th-label">思考过程</span>
      </template>
      <template #collapsed>
        <div class="th-preview">{{ preview }}</div>
      </template>
      <div class="th-body">{{ block.payload.text }}</div>
    </UiDisclosure>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { UiDisclosure, UiIcon } from '../ui'
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
.th-label { flex: 1; text-align: left; }
.th-body {
  padding: 0 var(--sp-2) var(--sp-1); white-space: pre-wrap;
  color: var(--text-2); font-size: var(--fs-sm); line-height: 1.5;
}
.th-preview {
  padding: 0 var(--sp-2) var(--sp-1); color: var(--text-3);
  font-size: var(--fs-xs); opacity: .8;
}
</style>
