<template>
  <!-- 未知块兜底：显示类型名 + 可展开原始 JSON（绝不丢数据）。
       Unknown block fallback: shows the type name + expandable raw JSON (never drops data). -->
  <div class="blk-unknown" :class="skin">
    <UiDisclosure v-model="open">
      <template #head>
        <UiIcon name="alert" :size="12" />
        <span class="u-type">{{ block.type }}</span>
        <span class="u-hint">未知块，点击查看原始数据</span>
      </template>
      <pre class="u-raw">{{ raw }}</pre>
    </UiDisclosure>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { UiDisclosure, UiIcon } from '../ui'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 未知块（原样保留）。Unknown block (preserved as-is).
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 是否展开原始 JSON。Whether raw JSON is expanded. */
const open = ref(false)

/** 块的原始 JSON（pretty-printed）。Raw block JSON. */
const raw = computed(() => {
  try { return JSON.stringify(props.block, null, 2) } catch { return String(props.block) }
})
</script>

<style scoped>
.blk-unknown {
  border: 1px dashed var(--bg-3); border-radius: var(--r-md);
  background: var(--bg-1);
}
.u-type { font-family: var(--font-mono); color: var(--text-2); }
.u-hint { opacity: .8; }
.u-raw {
  margin: 0; padding: var(--sp-2); overflow-x: auto;
  font-family: var(--font-mono); font-size: var(--fs-xs);
  color: var(--text-2); border-top: 1px solid var(--bg-2);
}
</style>
