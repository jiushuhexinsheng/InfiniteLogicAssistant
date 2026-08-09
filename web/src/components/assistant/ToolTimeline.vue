<template>
  <div class="tool-timeline">
    <div v-for="(step, i) in steps" :key="step.id" class="tt-step" :class="step.status">
      <div class="tt-row">
        <span class="tt-rail" :class="{ last: i === steps.length - 1 }"></span>
        <span class="tt-icon" :class="step.status">
          <Icon :name="step.icon || 'wrench'" :size="12" />
        </span>
        <span class="tt-name">{{ step.name }}</span>
        <span class="tt-status">{{ statusText(step.status) }}</span>
        <span v-if="step.durationMs != null" class="tt-dur">{{ (step.durationMs / 1000).toFixed(1) }}s</span>
        <button v-if="step.status === 'failed'" class="tt-act" title="重试" @click="emit('retry', step.id)">
          <Icon name="play" :size="11" />
        </button>
        <button v-if="['running', 'queued'].includes(step.status)" class="tt-act" title="取消" @click="emit('cancel', step.id)">
          <Icon name="close" :size="11" />
        </button>
        <button class="tt-expand" title="展开详情" @click="openId = openId === step.id ? '' : step.id">
          <Icon name="chevron-down" :size="11" :class="{ rot: openId === step.id }" />
        </button>
      </div>
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

defineProps<{ steps: ToolStep[] }>()

const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

const openId = ref('')

const STATUS_TEXT: Record<ToolStep['status'], string> = {
  queued: '排队', running: '执行中', done: '完成', failed: '失败',
}
function statusText(s: ToolStep['status']) { return STATUS_TEXT[s] || s }
</script>

<style scoped>
.tool-timeline { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.tt-step { position: relative; padding-left: 24px; }
.tt-row { display: flex; align-items: center; gap: 6px; font-size: 12px; min-height: 20px; }
.tt-rail {
  position: absolute; left: 5px; top: 16px; bottom: -6px; width: 2px;
  background: var(--border-base);
}
.tt-rail.last { display: none; }
.tt-icon {
  width: 14px; height: 14px; border-radius: 50%;
  background: #1e293b; color: var(--text-2);
  display: flex; align-items: center; justify-content: center;
  position: absolute; left: 0;
}
.tt-icon.running { color: var(--brand-c2); animation: tt-blink 1s infinite; }
.tt-icon.done { color: #34d399; }
.tt-icon.failed { color: #f87171; }
.tt-name { color: var(--text-1); }
.tt-status { font-size: 11px; color: var(--text-3); }
.tt-step.running .tt-status { color: var(--brand-c2); }
.tt-step.done .tt-status { color: #34d399; }
.tt-step.failed .tt-status { color: #f87171; }
.tt-dur { font-size: 11px; color: var(--text-3); margin-left: auto; }
.tt-act {
  background: none; border: none; color: var(--text-2); cursor: pointer;
  padding: 2px; display: flex;
}
.tt-act:hover { color: var(--brand-c2); }
.tt-expand {
  background: none; border: none; color: var(--text-3); cursor: pointer;
  padding: 2px; display: flex;
}
.tt-expand:hover { color: var(--text-1); }
.tt-expand .rot { transform: rotate(180deg); }
.tt-detail {
  margin-top: 4px; font-size: 11px; color: var(--text-2);
  background: #0f172a; padding: 6px 8px; border-radius: 6px;
  margin-left: 0;
}
.tool-args code {
  display: block; background: #1e293b; padding: 4px 6px; border-radius: 4px;
  margin-top: 2px; white-space: pre-wrap; word-break: break-all;
  color: #a5b4fc; max-height: 80px; overflow-y: auto;
}
.tool-result { margin-top: 4px; }
@keyframes tt-blink { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
</style>
