<template>
  <!-- 简约对话历史区域。Compact conversation history area. -->
  <div ref="scrollEl" class="mini-history">
    <!-- 空态：简洁提示。Empty state: simple prompt. -->
    <div v-if="!turns.length" class="mini-empty">
      <div class="empty-text">
        <b>开始对话</b>
        <span>输入文字，或说{{ wakeHint }}唤醒</span>
      </div>
    </div>

    <!-- 简约历史：用户（右对齐气泡） + AI（左对齐摘要气泡 + 工具徽章）。
         Compact history: user (right-aligned bubble) + AI (left-aligned summary bubble + tool badges). -->
    <template v-else>
      <div v-for="t in turns" :key="t.key" class="mini-turn">
        <!-- 用户输入：右侧品牌渐变气泡。User input: right-aligned brand gradient bubble. -->
        <div v-if="t.input" class="mini-bubble user">
          <div class="bubble-content">{{ t.input }}</div>
          <div class="bubble-tail user-tail"></div>
        </div>
        <!-- AI 摘要：左侧暗色气泡 + 工具徽章 + 完整记录入口。
             AI summary: left-aligned dark bubble + tool badges + full history link. -->
        <div class="mini-bubble ai">
          <div class="bubble-tail ai-tail"></div>
          <div class="bubble-content">
            <span class="mini-summary">{{ t.summary || (t.tools.length ? '已完成' : '…') }}</span>
            <div v-if="t.tools.length" class="tool-tags">
              <span v-for="name in t.tools" :key="name" class="mini-tool">
                <span class="tool-icon">⚡</span>
                {{ name }}
              </span>
            </div>
            <span class="mini-goto" @click.stop="emit('select')">
              查看完整记录
              <span class="arrow">→</span>
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { AsstState, ChatMessage } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'
import { summarizeBlock } from '../../blocks'

/**
 * 组件属性定义。Component props definition.
 * @property messages - 聊天消息列表。Chat message list.
 * @property state - 助手当前状态。Current assistant state.
 * @property visual - 状态对应的视觉配置。Visual configuration for the current state.
 * @property wakeHint - 唤醒词提示文案（可多个）。Wake keyword hint (may be plural).
 */
const props = defineProps<{
  messages: ChatMessage[]
  state: AsstState
  visual: StateVisual
  wakeHint: string
}>()

/**
 * 组件事件定义。Component events definition.
 * @event select - 用户点击"完整记录"时触发。Emitted when user clicks "full history" link.
 */
const emit = defineEmits<{ select: [] }>()

/** 对话轮次数据结构。Conversation turn data structure. */
interface Turn {
  key: string
  input: string
  summary: string
  tools: string[]
}

/**
 * 摘要：走块注册协议的 summarizeBlock（text 块剥 markdown 截 80 字，tool 显示
 * 徽章名等），无块的旧消息退化为纯文本摘要。不额外调 LLM。
 * Summarize via the registry's summarizeBlock (text blocks strip markdown and
 * truncate to 80 chars, tool blocks show their badge name, etc.); messages without
 * blocks degrade to a plain-text summary. No extra LLM call.
 */
function summarize(m: ChatMessage): string {
  if (m.blocks?.length) {
    return m.blocks
      .map(b => summarizeBlock(b))
      .filter(Boolean)
      .join(' ')
      .slice(0, 80)
  }
  const flat = m.text.replace(/\s*\n\s*/g, ' ').trim().replace(/[*`_~#>|]/g, '')
  return flat.length > 80 ? flat.slice(0, 80) + '…' : flat
}

/**
 * 摘要缓存：按消息 id 缓存 { text, summary }，仅当文本变化（流式增长）时才重算。
 * 避免 turns computed 每次消息变动都对整段历史（最多 200 条）重跑 summarize。
 * Summary cache: caches { text, summary } by message id, recalculates only when text changes (streaming growth).
 * Avoids re-running summarize on the entire history (up to 200 messages) on every turn computed trigger.
 */
const summaryCache = new Map<string, { text: string; summary: string }>()

/**
 * 带缓存的摘要获取。Get summary with cache.
 * @param m - 聊天消息。Chat message.
 */
function cachedSummary(m: ChatMessage): string {
  const hit = summaryCache.get(m.id)
  if (hit && hit.text === m.text) return hit.summary
  const summary = summarize(m)
  summaryCache.set(m.id, { text: m.text, summary })
  return summary
}

/**
 * 计算对话轮次列表。
 * user 消息暂存为 input，遇到 assistant 消息时产出 { input, summary, tools }；
 * 结尾未回复的 user 消息产出一条 '…' 占位。
 * Compute conversation turns.
 * User messages are staged as input; when an assistant message appears, emit { input, summary, tools };
 * an unreplied trailing user message produces a '…' placeholder.
 */
const turns = computed<Turn[]>(() => {
  const out: Turn[] = []
  let pendingInput = ''
  for (const m of props.messages) {
    if (m.role === 'user') {
      pendingInput = m.text
    } else if (m.role === 'assistant') {
      out.push({
        key: m.id,
        input: pendingInput,
        summary: cachedSummary(m),
        // 工具徽章来自 tool 块（toolCalls 已废弃，退化兼容旧消息）
        // Tool badges come from tool blocks (toolCalls deprecated; fallback for old messages).
        tools: m.blocks?.length
          ? m.blocks.filter(b => b.type === 'tool').map(b => b.payload.name)
          : (m.toolCalls || []).map(tc => tc.name),
      })
      pendingInput = ''
    } else if (m.role === 'system') {
      out.push({ key: m.id, input: '', summary: m.text, tools: [] })
    }
  }
  if (pendingInput) {
    out.push({ key: 'pending', input: pendingInput, summary: '…', tools: [] })
  }
  return out
})

/** 滚动容器元素引用。Scroll container element reference. */
const scrollEl = ref<HTMLElement | null>(null)

/**
 * 清空会话时同步清空摘要缓存，避免残留。
 * Clear summary cache when conversation is cleared to avoid stale data.
 */
watch(() => props.messages.length, (n) => {
  if (n === 0) summaryCache.clear()
})

/**
 * 新 turn 或最后一条文本增长（流式回复）时滚到底，保证最新内容可见。
 * Scroll to bottom when new turn arrives or last message text grows (streaming reply).
 */
watch(
  () => [props.messages.length, props.messages[props.messages.length - 1]?.text?.length],
  () => {
    nextTick(() => {
      if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
    })
  }
)
</script>

<style scoped>
/* 简约历史滚动容器。Compact history scroll container. */
.mini-history {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 8px 8px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, .2) transparent;
}

.mini-history::-webkit-scrollbar {
  width: 4px;
}

.mini-history::-webkit-scrollbar-track {
  background: transparent;
}

.mini-history::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, .3);
  border-radius: 2px;
}

/* ── 空态提示 ── */
.mini-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px 16px;
  text-align: center;
}

.empty-text {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.empty-text b {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-1);
}

.empty-text span {
  font-size: var(--fs-sm);
  color: var(--text-3);
  line-height: 1.5;
}

/* ── 对话轮次及入场动画 ── */
.mini-turn {
  display: flex;
  flex-direction: column;
  gap: 8px;
  animation: mini-in .4s var(--ease-out) both;
}

.mini-turn:nth-child(1) { animation-delay: 0s; }
.mini-turn:nth-child(2) { animation-delay: .05s; }
.mini-turn:nth-child(3) { animation-delay: .1s; }
.mini-turn:nth-child(4) { animation-delay: .15s; }
.mini-turn:nth-child(5) { animation-delay: .2s; }

@keyframes mini-in {
  from { opacity: 0; transform: translateY(12px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

/* ── 气泡基础样式 ── */
.mini-bubble {
  position: relative;
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: var(--fs-sm);
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}

.bubble-content {
  position: relative;
  z-index: 1;
}

/* ── 用户气泡 ── */
.mini-bubble.user {
  align-self: flex-end;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #ffffff;
  font-weight: 500;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 12px rgba(99, 102, 241, .3);
}

/* 用户气泡尾巴 */
.bubble-tail {
  position: absolute;
  bottom: 6px;
  width: 12px;
  height: 12px;
  z-index: 0;
}

.user-tail {
  right: -6px;
  background: linear-gradient(135deg, #8b5cf6, #8b5cf6);
  clip-path: polygon(0 0, 100% 0, 0 100%);
}

/* ── AI 气泡 ── */
.mini-bubble.ai {
  align-self: flex-start;
  background: linear-gradient(180deg, rgba(30, 41, 59, .95), rgba(15, 23, 42, .95));
  color: var(--text-1);
  border-bottom-left-radius: 4px;
  border: 1px solid rgba(103, 232, 249, .15);
  box-shadow: 0 4px 16px rgba(0, 0, 0, .2);
}

.ai-tail {
  left: -6px;
  background: linear-gradient(180deg, rgba(30, 41, 59, .95), rgba(15, 23, 42, .95));
  clip-path: polygon(100% 0, 100% 100%, 0 0);
}

/* AI 摘要文本 */
.mini-summary {
  display: block;
  margin-bottom: 8px;
  line-height: 1.6;
}

/* ── 工具标签 ── */
.tool-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.mini-tool {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  color: var(--brand-c2);
  background: rgba(103, 232, 249, .08);
  border: 1px solid rgba(103, 232, 249, .2);
  border-radius: 8px;
  padding: 4px 10px;
  transition: all .2s ease;
}

.mini-tool:hover {
  background: rgba(103, 232, 249, .15);
  border-color: rgba(103, 232, 249, .3);
}

.tool-icon {
  font-size: 10px;
}

/* ── 完整记录入口 ── */
.mini-goto {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-3);
  cursor: pointer;
  transition: all .2s ease;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(148, 163, 184, .05);
  border: 1px solid transparent;
}

.mini-goto:hover {
  color: var(--brand-c2);
  background: rgba(103, 232, 249, .08);
  border-color: rgba(103, 232, 249, .15);
}

.arrow {
  transition: transform .2s ease;
}

.mini-goto:hover .arrow {
  transform: translateX(4px);
}
</style>
