<template>
  <div class="msg-item" :class="message.role">
    <div class="msg-bubble" :class="message.role">
      <div class="msg-text">{{ message.text }}</div>
      <!-- 工具调用 -->
      <div v-if="message.toolCalls?.length" class="msg-tools">
        <div
          v-for="tc in message.toolCalls"
          :key="tc.id"
          class="tool-tag"
          :class="tc.status"
          @click="expandedToolId = expandedToolId === tc.id ? '' : tc.id"
        >
          <span class="tool-icon">{{ toolIcon(tc) }}</span>
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
    <div class="msg-time">{{ formatTime(message.timestamp) }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ChatMessage, ToolCall } from '../../composables/useAssistant'

defineProps<{ message: ChatMessage }>()

const expandedToolId = ref('')

function toolIcon(tc: ToolCall) {
  const map: Record<string, string> = { chat: '💬' }
  return map[tc.name] || '🔧'
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
  flex-direction: column;
  gap: 2px;
}
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
.msg-time {
  font-size: 10px;
  color: var(--text-3);
  padding: 0 4px;
}
.msg-item.user .msg-time { text-align: right; }
.msg-item.assistant .msg-time { text-align: left; }
.msg-item.system .msg-time { text-align: center; }

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
.tool-icon { font-size: 12px; }
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
