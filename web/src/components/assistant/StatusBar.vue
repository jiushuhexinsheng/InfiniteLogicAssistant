<template>
  <div class="panel-status" :class="[state, visual.grad === 'rainbow' ? 'st-rainbow' : '']">
    <span
      class="status-dot"
      :style="{ background: visual.color, boxShadow: `0 0 8px ${visual.color}66` }"
    ></span>
    <span class="status-label">{{ statusDisplay }}</span>
    <span v-if="statusLine" class="status-line">{{ statusLine }}</span>
    <button v-if="showEnableButton" class="status-toggle" @click="emit('toggleWake')">👂 开启</button>
    <button v-else class="status-toggle stop" @click="emit('toggleWake')">⏹ 关闭</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AsstState } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  state: AsstState
  visual: StateVisual
  statusLine: string
  partialText: string
  wakeEnabled: boolean
}>()

const emit = defineEmits<{ toggleWake: [] }>()

// 保留原逻辑：聆听/录音时优先显示实时转写 partialText
const statusDisplay = computed(() => {
  if (props.partialText && (props.state === 'listening' || props.state === 'recording')) {
    return props.partialText
  }
  const label = typeof props.visual.label === 'function' ? props.visual.label('') : props.visual.label
  return label
})

const showEnableButton = computed(() =>
  ['idle', 'error', 'done'].includes(props.state)
)
</script>

<style scoped>
.panel-status {
  display: flex;
  align-items: center;
  padding: 8px 14px;
  gap: 8px;
  border-bottom: 1px solid var(--border-base);
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 0.3s;
}
.status-label {
  flex: 1;
  font-size: 13px;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-line {
  font-size: 11px;
  color: #f97316;
  white-space: nowrap;
  animation: blink 1s infinite;
}
.status-toggle {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid #22c55e;
  background: #22c55e20;
  color: #22c55e;
  cursor: pointer;
  white-space: nowrap;
}
.status-toggle.stop {
  border-color: #ef4444;
  background: #ef444420;
  color: #ef4444;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* 状态灯动画 */
.panel-status.listening .status-dot {
  animation: breathe 1.4s ease-in-out infinite;
}
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 4px #34d399; }
  50% { box-shadow: 0 0 12px #34d399, 0 0 20px #34d39944; }
}
.panel-status.recording .status-dot {
  animation: blink 0.6s infinite;
}
.panel-status.thinking .status-dot,
.panel-status.tool_calling .status-dot,
.panel-status.transcribing .status-dot {
  background: transparent !important;
  border: 2px solid rgba(255, 255, 255, .15);
  border-top-color: #f97316;
  animation: dot-spin 0.8s linear infinite;
}
.panel-status.tool_calling .status-dot { border-top-color: #06b6d4; }
.panel-status.transcribing .status-dot { border-top-color: #a855f7; }
@keyframes dot-spin { to { transform: rotate(360deg); } }

/* 彩虹状态（聆听/录音） */
.panel-status.st-rainbow .status-dot {
  background: var(--rainbow) !important;
  animation: rainbow-hue 2.5s linear infinite;
}
</style>
