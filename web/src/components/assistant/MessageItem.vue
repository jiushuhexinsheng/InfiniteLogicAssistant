<template>
  <div class="msg-item" :class="message.role">
    <span v-if="message.role !== 'system'" class="msg-avatar" :class="message.role">
      <UiIcon :name="message.role === 'assistant' ? 'brain' : 'user'" :size="14" />
    </span>
    <div class="msg-body">
      <div class="msg-meta">
        <span class="msg-role">{{ roleName }}</span>
        <span class="msg-time">{{ formatTime(message.timestamp) }}</span>
      </div>
      <div class="msg-bubble" :class="message.role">
        <MarkdownRenderer v-if="message.role !== 'system'" :text="message.text" />
        <div v-else class="msg-text">{{ message.text }}</div>
        <ToolTimeline
          v-if="message.toolCalls?.length"
          :steps="timelineSteps"
          @retry="emit('retry', $event)"
          @cancel="emit('cancel', $event)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { UiIcon } from '../ui'
import MarkdownRenderer from '../MarkdownRenderer.vue'
import ToolTimeline from './ToolTimeline.vue'
import type { ChatMessage, ToolCall } from '../../composables/useAssistant'
import type { ToolStep } from '../../types'

const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

const roleName = computed(() => {
  switch (props.message.role) {
    case 'user': return '你'
    case 'assistant': return '小逻'
    default: return '系统'
  }
})

function toolIcon(tc: ToolCall) { return 'wrench' }
function toolLabel(tc: ToolCall) { return tc.name }

const timelineSteps = computed<ToolStep[]>(() =>
  (props.message.toolCalls || []).map((tc) => ({
    id: tc.id,
    name: toolLabel(tc),
    icon: toolIcon(tc),
    status: tc.status === 'pending' ? 'queued' : tc.status,
    durationMs: (tc as ToolCall & { durationMs?: number }).durationMs,
    args: tc.args,
    result: tc.result,
  }))
)

function formatTime(ts: number) {
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.msg-item { display: flex; gap: 8px; align-items: flex-start; animation: msg-in .32s var(--ease-out) both; }
.msg-item.system { justify-content: center; }
@keyframes msg-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.msg-avatar {
  width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; margin-top: 2px;
}
.msg-avatar.assistant { background: var(--brand-grad); color: var(--text-on-brand); }
.msg-avatar.user { background: var(--bg-3); color: var(--text-2); }

.msg-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.msg-meta { display: flex; align-items: baseline; gap: 6px; padding: 0 4px 2px; }
.msg-role { font-size: 11px; color: var(--text-3); }
.msg-time { font-size: 10px; color: var(--text-3); opacity: .8; }
.msg-item.user .msg-meta { flex-direction: row-reverse; }

.msg-bubble {
  position: relative; max-width: 90%;
  padding: 8px 12px; border-radius: var(--r-lg);
  font-size: var(--fs-sm); line-height: 1.5; word-break: break-word;
}
.msg-bubble.user {
  align-self: flex-end;
  background: var(--bubble-user); color: var(--bubble-user-text); font-weight: 500;
  border-bottom-right-radius: 4px;
}
.msg-bubble.user::after {
  content: ''; position: absolute; right: -5px; bottom: 6px;
  width: 10px; height: 10px; background: var(--brand-c3);
  border-bottom-right-radius: 3px; transform: rotate(45deg);
}
.msg-bubble.assistant {
  align-self: flex-start;
  background: var(--bubble-ai); color: var(--text-1);
  border-left: 2px solid var(--bubble-ai-border);
  border-bottom-left-radius: 4px;
}
.msg-bubble.system {
  align-self: center; background: #7f1d1d; color: #fca5a5;
  font-size: 12px; max-width: 80%; text-align: center;
}
.msg-text { white-space: pre-wrap; }
</style>
