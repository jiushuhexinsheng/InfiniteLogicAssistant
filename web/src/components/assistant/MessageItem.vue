<template>
  <div class="msg-item" :class="message.role">
    <span v-if="message.role !== 'system'" class="msg-avatar" :class="message.role">
      <Icon :name="message.role === 'assistant' ? 'brain' : 'user'" :size="14" />
    </span>
    <div class="msg-body">
      <div class="msg-meta">
        <span class="msg-role">{{ roleName }}</span>
        <span class="msg-time">{{ formatTime(message.timestamp) }}</span>
      </div>
      <div class="msg-bubble" :class="message.role">
        <MarkdownRenderer v-if="message.role !== 'system'" :text="message.text.slice(0, revealed)" />
        <div v-else class="msg-text">{{ message.text }}</div>
        <!-- 工具调用：纵向时间轴 -->
        <ToolTimeline
          v-if="message.toolCalls?.length"
          :steps="timelineSteps"
          @retry="emit('retry', $event)"
          @cancel="emit('cancel', $event)"
        />
        <slot v-if="message.toolCalls?.length" name="tool-actions" :tool="message.toolCalls[0]"></slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Icon from '../Icon.vue'
import MarkdownRenderer from '../MarkdownRenderer.vue'
import ToolTimeline from './ToolTimeline.vue'
import type { ChatMessage, ToolCall } from '../../composables/useAssistant'
import type { ToolStep } from '../../types'

const props = defineProps<{ message: ChatMessage; typewriter?: boolean }>()

const emit = defineEmits<{ retry: [id: string]; cancel: [id: string]; typed: [id: string] }>()

// ── 流式打字效果（仅新助手消息，用 animatedIds 防重播）──
const revealed = ref(0)
let twTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  const full = props.message.text.length
  if (props.typewriter && props.message.role === 'assistant' && full > 0) {
    revealed.value = 0
    twTimer = setInterval(() => {
      revealed.value += 2
      if (revealed.value >= full) {
        revealed.value = full
        if (twTimer) { clearInterval(twTimer); twTimer = null }
        emit('typed', props.message.id)
      }
    }, 20)
  } else {
    revealed.value = full
  }
})
onUnmounted(() => { if (twTimer) clearInterval(twTimer) })

const roleName = computed(() => {
  switch (props.message.role) {
    case 'user': return '你'
    case 'assistant': return '小逻'
    default: return '系统'
  }
})

function toolIcon(tc: ToolCall) {
  const map: Record<string, string> = { chat: 'chat' }
  return map[tc.name] || 'wrench'
}

function toolLabel(tc: ToolCall) {
  const map: Record<string, string> = { chat: '对话' }
  return map[tc.name] || tc.name
}

// ToolCall → ToolStep（pending → queued 时间轴展示名）
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
.msg-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.msg-item.system { justify-content: center; }

/* 头像 */
.msg-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}
.msg-avatar.assistant {
  background: var(--brand-grad);
  color: #0f172a;
}
.msg-avatar.user {
  background: #334155;
  color: var(--text-2);
}

.msg-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }

/* 头部：角色名 + 时间 */
.msg-meta {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 0 4px 2px;
}
.msg-role { font-size: 11px; color: var(--text-3); }
.msg-time { font-size: 10px; color: var(--text-3); opacity: .8; }
.msg-item.user .msg-meta { flex-direction: row-reverse; }

.msg-bubble {
  max-width: 90%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}
/* 用户气泡：品牌渐变背景 */
.msg-bubble.user {
  align-self: flex-end;
  background: var(--brand-grad);
  color: #fff;
  border-bottom-right-radius: 4px;
}
/* 助手气泡：暗色底 + 品牌渐变左边框 */
.msg-bubble.assistant {
  align-self: flex-start;
  background: #334155;
  color: var(--text-1);
  border-left: 2px solid var(--brand-c2);
  border-bottom-left-radius: 4px;
}
.msg-bubble.system {
  align-self: center;
  background: #7f1d1d;
  color: #fca5a5;
  font-size: 12px;
  max-width: 80%;
  text-align: center;
}
.msg-text { white-space: pre-wrap; }
</style>
