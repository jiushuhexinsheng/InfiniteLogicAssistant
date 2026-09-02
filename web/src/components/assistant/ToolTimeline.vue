<template>
  <!-- 工具调用时间线：展示每个工具步骤的状态、耗时及详情。Tool call timeline: shows status, duration and details for each tool step. -->
  <div class="tool-timeline">
    <div v-for="(step, i) in steps" :key="step.id" class="tt-step" :class="step.status">
      <div class="tt-row">
        <!-- 连接线（最后一个步骤不显示）。Connector rail (hidden for last step). -->
        <span class="tt-rail" :class="{ last: i === steps.length - 1 }"></span>
        <!-- 步骤状态图标。Step status icon. -->
        <span class="tt-icon" :class="step.status">
          <Icon :name="step.icon || 'wrench'" :size="12" />
        </span>
        <!-- 步骤名称。Step name. -->
        <span class="tt-name">{{ step.name }}</span>
        <!-- 状态文本。Status text. -->
        <span class="tt-status">{{ statusText(step.status) }}</span>
        <!-- 耗时（毫秒转秒）。Duration (ms to seconds). -->
        <span v-if="step.durationMs != null" class="tt-dur">{{ (step.durationMs / 1000).toFixed(1) }}s</span>
        <!-- 重试按钮（失败时显示）。Retry button (shown when failed). -->
        <button v-if="step.status === 'failed'" class="tt-act" title="重试" @click="emit('retry', step.id)">
          <Icon name="play" :size="11" />
        </button>
        <!-- 停止按钮（运行中/排队时显示）。Cancel button (shown when running/queued). -->
        <button v-if="['running', 'queued'].includes(step.status)" class="tt-act" title="停止" @click="emit('cancel', step.id)">
          <Icon name="close" :size="11" />
        </button>
        <!-- 展开/折叠详情按钮。Expand/collapse details button. -->
        <button class="tt-expand" title="展开详情" @click="openId = openId === step.id ? '' : step.id">
          <Icon name="chevron-down" :size="11" :class="{ rot: openId === step.id }" />
        </button>
      </div>
      <!-- 步骤详情（参数和结果）。Step details (arguments and result). -->
      <div v-if="openId === step.id" class="tt-detail">
        <div class="tool-args">
          <strong>参数:</strong>
          <code>{{ JSON.stringify(step.args, null, 2) }}</code>
        </div>
        <div v-if="step.result" class="tool-result">
          <strong>结果:</strong> {{ step.result }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Icon from '../Icon.vue'
import type { ToolStep } from '../../types'

/**
 * 组件属性定义。Component props definition.
 * @property steps - 工具步骤列表。Tool step list.
 */
defineProps<{ steps: ToolStep[] }>()

/**
 * 组件事件定义。Component events definition.
 * @event retry - 重试失败的工具调用。Retry a failed tool call.
 * @event cancel - 取消运行中的工具调用。Cancel a running tool call.
 */
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

/** 当前展开详情的步骤 ID。Currently expanded step ID. */
const openId = ref('')

/** 状态文本映射表。Status text mapping. */
const STATUS_TEXT: Record<ToolStep['status'], string> = {
  queued: '排队', running: '执行中', done: '完成', failed: '失败',
}

/**
 * 获取状态的中文显示文本。Get Chinese display text for a status.
 * @param s - 工具步骤状态。Tool step status.
 */
function statusText(s: ToolStep['status']) { return STATUS_TEXT[s] || s }
</script>

<style scoped>
/* 工具时间线容器。Tool timeline container. */
.tool-timeline { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
/* 单个步骤。Single step. */
.tt-step { position: relative; padding-left: 24px; }
/* 步骤行布局。Step row layout. */
.tt-row { display: flex; align-items: center; gap: 6px; font-size: 12px; min-height: 20px; }
/* 连接线。Connector rail. */
.tt-rail {
  position: absolute; left: 5px; top: 16px; bottom: -6px; width: 2px;
  background: var(--border-base);
}
.tt-rail.last { display: none; }
/* 步骤状态图标。Step status icon. */
.tt-icon {
  width: 14px; height: 14px; border-radius: 50%;
  background: #1e293b; color: var(--text-2);
  display: flex; align-items: center; justify-content: center;
  position: absolute; left: 0;
}
.tt-icon.running { color: var(--brand-c2); animation: tt-blink 1s infinite; }
.tt-icon.done { color: #34d399; }
.tt-icon.failed { color: #f87171; }
/* 步骤名称。Step name. */
.tt-name { color: var(--text-1); }
/* 状态文本（颜色随状态变化）。Status text (color changes with status). */
.tt-status { font-size: 11px; color: var(--text-3); }
.tt-step.running .tt-status { color: var(--brand-c2); }
.tt-step.done .tt-status { color: #34d399; }
.tt-step.failed .tt-status { color: #f87171; }
/* 耗时显示。Duration display. */
.tt-dur { font-size: 11px; color: var(--text-3); margin-left: auto; }
/* 操作按钮（重试/停止）。Action buttons (retry/cancel). */
.tt-act {
  background: none; border: none; color: var(--text-2); cursor: pointer;
  padding: 2px; display: flex;
}
.tt-act:hover { color: var(--brand-c2); }
/* 展开详情按钮。Expand details button. */
.tt-expand {
  background: none; border: none; color: var(--text-3); cursor: pointer;
  padding: 2px; display: flex;
}
.tt-expand:hover { color: var(--text-1); }
.tt-expand .rot { transform: rotate(180deg); }
/* 详情面板。Details panel. */
.tt-detail {
  margin-top: 4px; font-size: 11px; color: var(--text-2);
  background: #0f172a; padding: 6px 8px; border-radius: 6px;
  margin-left: 0;
}
/* 参数代码块。Arguments code block. */
.tool-args code {
  display: block; background: #1e293b; padding: 4px 6px; border-radius: 4px;
  margin-top: 2px; white-space: pre-wrap; word-break: break-all;
  color: #a5b4fc; max-height: 80px; overflow-y: auto;
}
/* 结果文本。Result text. */
.tool-result { margin-top: 4px; }
/* 运行中闪烁动画。Running blink animation. */
@keyframes tt-blink { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
</style>
