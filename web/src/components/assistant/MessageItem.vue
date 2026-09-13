<template>
  <!-- 单条消息项，按角色（user/assistant/system）区分样式。Single message item, styled by role (user/assistant/system). -->
  <div class="msg-item" :class="message.role">
    <!-- 头像（系统消息不显示）。Avatar (hidden for system messages). -->
    <span v-if="message.role !== 'system'" class="msg-avatar" :class="message.role">
      <UiIcon :name="message.role === 'assistant' ? 'brain' : 'user'" :size="14" />
    </span>
    <div class="msg-body">
      <!-- 消息元信息：角色名 + 时间戳。Message meta: role name + timestamp. -->
      <div class="msg-meta">
        <span class="msg-role">{{ roleName }}</span>
        <span class="msg-time">{{ formatTime(message.timestamp) }}</span>
      </div>
      <!-- 消息气泡：助手消息渲染 Markdown，系统消息纯文本。Message bubble: assistant renders Markdown, system uses plain text. -->
      <div class="msg-bubble" :class="message.role">
        <MarkdownRenderer v-if="message.role !== 'system'" :text="message.text" />
        <div v-else class="msg-text">{{ message.text }}</div>
        <!-- 工具调用时间线（助手消息有工具调用时显示）。Tool timeline (shown when assistant message has tool calls). -->
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

/**
 * 组件属性定义。Component props definition.
 * @property message - 聊天消息对象。Chat message object.
 */
const props = defineProps<{ message: ChatMessage }>()

/**
 * 组件事件定义。Component events definition.
 * @event retry - 重试失败的工具调用。Retry a failed tool call.
 * @event cancel - 取消运行中的工具调用。Cancel a running tool call.
 */
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

/**
 * 计算角色显示名称：user→'你', assistant→'衍衡', system→'系统'。
 * Compute role display name: user→'你', assistant→'衍衡', system→'系统'.
 */
const roleName = computed(() => {
  switch (props.message.role) {
    case 'user': return '你'
    case 'assistant': return '衍衡'
    default: return '系统'
  }
})

/**
 * 获取工具调用图标名称。Get tool call icon name.
 * @param tc - 工具调用对象。Tool call object.
 */
function toolIcon(tc: ToolCall) { return 'wrench' }

/**
 * 获取工具调用显示标签。Get tool call display label.
 * @param tc - 工具调用对象。Tool call object.
 */
function toolLabel(tc: ToolCall) { return tc.name }

/**
 * 将消息的 toolCalls 转换为时间线步骤数据。
 * Convert message toolCalls to timeline step data.
 */
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

/**
 * 格式化时间戳为中文格式（HH:MM）。Format timestamp to Chinese format (HH:MM).
 * @param ts - 时间戳毫秒数。Timestamp in milliseconds.
 */
function formatTime(ts: number) {
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
/* 消息项容器及入场动画。Message item container and entrance animation. */
.msg-item { display: flex; gap: 8px; align-items: flex-start; animation: msg-in .32s var(--ease-out) both; }
.msg-item.system { justify-content: center; }
@keyframes msg-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

/* 消息头像。Message avatar. */
.msg-avatar {
  width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; margin-top: 2px;
}
.msg-avatar.assistant { background: var(--brand-grad); color: var(--text-on-brand); }
.msg-avatar.user { background: var(--bg-3); color: var(--text-2); }

/* 消息内容区域。Message body area. */
.msg-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
/* 消息元信息行。Message meta line. */
.msg-meta { display: flex; align-items: baseline; gap: 6px; padding: 0 4px 2px; }
.msg-role { font-size: 11px; color: var(--text-3); }
.msg-time { font-size: 10px; color: var(--text-3); opacity: .8; }
.msg-item.user .msg-meta { flex-direction: row-reverse; }

/* 消息气泡。Message bubble. */
.msg-bubble {
  position: relative; max-width: 90%;
  padding: 8px 12px; border-radius: var(--r-lg);
  font-size: var(--fs-sm); line-height: 1.5; word-break: break-word;
}
/* 用户气泡：右对齐品牌渐变。User bubble: right-aligned brand gradient. */
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
/* 助手气泡：左对齐暗色 + 品牌左边框。Assistant bubble: left-aligned dark with brand left border. */
.msg-bubble.assistant {
  align-self: flex-start;
  background: var(--bubble-ai); color: var(--text-1);
  border-left: 2px solid var(--bubble-ai-border);
  border-bottom-left-radius: 4px;
}
/* 系统气泡：居中红色警告风格。System bubble: centered red warning style. */
.msg-bubble.system {
  align-self: center; background: #7f1d1d; color: #fca5a5;
  font-size: 12px; max-width: 80%; text-align: center;
}
.msg-text { white-space: pre-wrap; }
</style>
