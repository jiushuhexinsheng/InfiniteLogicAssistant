<template>
  <!-- 工具调用模块：复用 ToolTimeline 渲染单工具步骤（状态/耗时/参数/结果折叠）。
       Tool block: reuses ToolTimeline for a single step (status/duration/args/output). -->
  <div class="blk-tool" :class="[skin, block.payload.status]">
    <ToolTimeline
      :steps="[step]"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
    />
    <div v-if="block.agent" class="tool-agent">{{ block.agent }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ToolTimeline from '../assistant/ToolTimeline.vue'
import type { Block, Skin } from '../../blocks/types'
import type { ToolStep } from '../../types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 工具块。Tool block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/**
 * 组件事件定义。Component events definition.
 * @event retry - 重试工具。Retry tool.
 * @event cancel - 取消工具。Cancel tool.
 */
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

/** 工具块 payload → ToolTimeline 步骤（复用既有时间线组件）。
 *  Tool block payload → ToolTimeline step (reuses the existing timeline component). */
const step = computed<ToolStep>(() => {
  const p = props.block.payload
  const status = p.status === 'ok' ? 'done' : p.status === 'error' ? 'failed' : p.status === 'running' ? 'running' : 'queued'
  return {
    id: p.call_id || props.block.id,
    name: p.name,
    icon: 'wrench',
    status,
    durationMs: p.duration_ms,
    args: p.args,
    result: p.output_preview || p.output,
  }
})
</script>

<style scoped>
.blk-tool { position: relative; }
.tool-agent {
  margin-top: var(--sp-1); padding-left: var(--sp-3);
  font-size: var(--fs-xs); color: var(--text-3);
}
</style>
