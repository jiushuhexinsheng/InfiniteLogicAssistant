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
        <div class="msg-text">{{ message.text }}</div>
        <!-- 工具调用（Task 7 替换为 ToolTimeline） -->
        <div v-if="message.toolCalls?.length" class="msg-tools">
          <div
            v-for="tc in message.toolCalls"
            :key="tc.id"
            class="tool-tag"
            :class="tc.status"
            @click="expandedToolId = expandedToolId === tc.id ? '' : tc.id"
          >
            <Icon :name="toolIcon(tc)" :size="12" />
            <span class="tool-name">{{ toolLabel(tc) }}</span>
            <span class="tool-status-badge">{{ tc.status }}</span>
          </div>
          <div v-if="expandedToolId === message.toolCalls[0]?.id" class="tool-detail">
            <div class="tool-args">
              <strong>参数:</strong>
              <code>{{ JSON.stringify(message.toolCalls[0].args, null, 2) }}</code>
            </div>
            <div v-if="message.toolCalls[0].result" class="tool-result">
              <strong>结果:</strong> {{ message.toolCalls[0].result }}
            </div>
          </div>
          <slot name="tool-actions" :tool="message.toolCalls[0]"></slot>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import Icon from '../Icon.vue'
import type { ChatMessage, ToolCall } from '../../composables/useAssistant'

const props = defineProps<{ message: ChatMessage }>()

const expandedToolId = ref('')

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

/* 工具调用 */
.msg-tools {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tool-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  background: #1e293b;
  cursor: pointer;
  align-self: flex-start;
}
.tool-tag.running { border-left: 3px solid #f97316; }
.tool-tag.done { border-left: 3px solid #22c55e; }
.tool-tag.failed { border-left: 3px solid #ef4444; }
.tool-name { color: var(--text-2); }
.tool-status-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 8px;
  margin-left: 4px;
}
.tool-tag.running .tool-status-badge { background: #f9731620; color: #f97316; }
.tool-tag.done .tool-status-badge { background: #22c55e20; color: #22c55e; }
.tool-tag.failed .tool-status-badge { background: #ef444420; color: #ef4444; }

.tool-detail {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-2);
  background: #0f172a;
  padding: 6px 8px;
  border-radius: 6px;
  max-width: 100%;
  overflow: hidden;
}
.tool-detail strong { color: var(--text-1); }
.tool-detail code {
  display: block;
  background: #1e293b;
  padding: 4px 6px;
  border-radius: 4px;
  margin-top: 2px;
  font-size: 11px;
  color: #a5b4fc;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 80px;
  overflow-y: auto;
}
.tool-result { margin-top: 4px; }
</style>
