<template>
  <div ref="scrollEl" class="mini-history">
    <!-- 空态：状态相关提示 -->
    <div v-if="!turns.length" class="mini-empty">
      <template v-if="state === 'listening'">
        <span class="mini-eq"><i></i><i></i><i></i></span>
        聆听中，说"{{ wakeKeyword }}"唤醒我
      </template>
      <template v-else-if="state === 'recording'">🎙️ 录音中…</template>
      <template v-else-if="state === 'transcribing'">✨ 识别中…</template>
      <template v-else>说"{{ wakeKeyword }}"开始对话，或输入文字</template>
    </div>

    <!-- 简约历史：用户（右对齐气泡） + AI（左对齐摘要气泡 + 工具徽章） -->
    <template v-else>
      <div v-for="t in turns" :key="t.key" class="mini-turn">
        <!-- 用户输入：右侧品牌渐变气泡 -->
        <div v-if="t.input" class="mini-bubble user">{{ t.input }}</div>
        <!-- AI 摘要：左侧暗色气泡 + 工具徽章 + 完整记录入口 -->
        <div class="mini-bubble ai">
          <span class="mini-summary">{{ t.summary || (t.tools.length ? '已完成' : '…') }}</span>
          <span v-for="name in t.tools" :key="name" class="mini-tool">{{ name }}</span>
          <span class="mini-goto" @click.stop="emit('select')">完整记录 →</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { AsstState, ChatMessage } from '../../composables/useAssistant'
import type { StateVisual } from '../../composables/useAssistantVisuals'

const props = defineProps<{
  messages: ChatMessage[]
  state: AsstState
  visual: StateVisual
  wakeKeyword: string
}>()

const emit = defineEmits<{ select: [] }>()

interface Turn {
  key: string
  input: string
  summary: string
  tools: string[]
}

/** 摘要：取首个非空行、剥 markdown 记号、截断。不额外调 LLM。 */
function summarize(text: string): string {
  const line = (text.split('\n').map(s => s.trim()).find(Boolean) || '').replace(/[*`_~#>|]/g, '')
  return line.length > 60 ? line.slice(0, 60) + '…' : line
}

// user 暂存为 input，遇 assistant 产出 { input, summary, tools }；结尾未回复的 user 产出一条 '…'
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
        summary: summarize(m.text),
        tools: (m.toolCalls || []).map(tc => tc.name),
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

const scrollEl = ref<HTMLElement | null>(null)

// 新 turn 或最后一条文本增长（流式回复）时滚到底，保证最新内容可见
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
.mini-history {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 2px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mini-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--text-3);
  font-size: 12px;
  text-align: center;
  padding: 16px;
}

/* 空态 EQ 动画 */
.mini-eq { display: inline-flex; align-items: flex-end; gap: 2px; height: 14px; }
.mini-eq i {
  width: 3px; height: 100%; background: var(--brand-c2); border-radius: 1px;
  animation: eq-bounce 1s ease-in-out infinite;
}
.mini-eq i:nth-child(2) { animation-delay: .15s; }
.mini-eq i:nth-child(3) { animation-delay: .3s; }
@keyframes eq-bounce { 0%,100% { height: 30%; } 50% { height: 100%; } }

.mini-turn { display: flex; flex-direction: column; gap: 4px; }

/* 气泡：用户右对齐品牌渐变 / AI 左对齐暗色 + 品牌左边框（与完整聊天一致） */
.mini-bubble {
  max-width: 88%;
  padding: 6px 10px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}
.mini-bubble.user {
  align-self: flex-end;
  background: var(--brand-grad);
  color: #0f172a;
  border-bottom-right-radius: 4px;
}
.mini-bubble.ai {
  align-self: flex-start;
  background: #334155;
  color: var(--text-1);
  border-left: 2px solid var(--brand-c2);
  border-bottom-left-radius: 4px;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
}

.mini-summary { flex: 1; min-width: 0; }
.mini-tool {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--brand-c2);
  border: 1px solid var(--border-base);
  border-radius: 4px;
  padding: 1px 5px;
  background: rgba(34, 211, 238, .06);
}
.mini-goto {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-3);
  cursor: pointer;
  text-decoration: underline dotted;
}
.mini-goto:hover { color: var(--brand-c2); }
</style>
