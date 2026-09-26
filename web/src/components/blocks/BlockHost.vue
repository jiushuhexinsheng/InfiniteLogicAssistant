<template>
  <!-- 块列表宿主：按注册表动态渲染各块类型（新块即插即用，页面零改动）。
       同级块列表经 provide 下发（汇总卡按 block_ids 过滤渲染本轮回看）。
       Block list host: renders each block type via the registry (new blocks plug
       in with zero page changes). The sibling block list is provided downward
       (the summary card filters by block_ids to render the turn review). -->
  <div class="block-host" :class="`skin-${skin}`">
    <component
      :is="getBlockSpec(b.type).component"
      v-for="b in blocks"
      :key="b.id"
      :block="b"
      :skin="skin"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { provide } from 'vue'
// 从 index 导入（而非 registry）：index 执行全部内置块的注册副作用，
// 否则宿主拿到的注册表是空的。
// Import from index (not registry): index runs the registration side effects of
// all built-in blocks, otherwise the host sees an empty registry.
import { getBlockSpec } from '../../blocks'
import { BLOCKS_CONTEXT } from '../../blocks/context'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property blocks - 消息块列表。Message block list.
 * @property skin - 渲染皮肤（full/summary/task）。Render skin.
 */
const props = defineProps<{ blocks: Block[]; skin?: Skin }>()

/**
 * 组件事件定义（工具重试/取消从块内上抛到 useChat）。
 * Component events (tool retry/cancel bubble up to useChat).
 */
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

// 同级块列表注入（汇总卡本轮回看按 block_ids 过滤渲染）
// Provide sibling blocks (the summary card filters by block_ids for the turn review).
provide(BLOCKS_CONTEXT, () => props.blocks)
</script>

<style scoped>
.block-host { display: flex; flex-direction: column; gap: var(--sp-2); }
/* task 皮肤：平铺紧凑日志（无气泡尾巴的密度差异由各块组件按 skin 控制）。
   task skin: flat compact log (density differences controlled per block via skin). */
.block-host.skin-task { gap: var(--sp-1); }
</style>
