<template>
  <div class="mini-history">
    <!-- 空态：状态相关提示 -->
    <div v-if="!turns.length" class="mini-empty">
      <template v-if="state === 'listening'">
        <span class="mini-eq"><i></i><i></i><i></i></span>
        聆听中，说"{{ wakeKeyword }}"唤醒我
      </template>
      <template v-else-if="state === 'recording'">🎙️ 录音中…</template>
      <template v-else-if="state === 'transcribing'">✨ 识别中…</template>
      <template v-else>说"{{ wakeKeyword }}"开始对话，或在下方面板输入文字</template>
    </div>

    <!-- 简约历史：每轮 = 输入 + 摘要 + 工具徽章 -->
    <div
      v-for="t in turns"
      :key="t.key"
      class="mini-turn"
      @click="emit('select')"
    >
      <div v-if="t.input" class="mini-input">{{ t.input }}</div>
      <div class="mini-line">
        <span class="mini-summary">{{ t.summary || (t.tools.length ? '已完成' : '…') }}</span>
        <span v-for="name in t.tools" :key="name" class="mini-tool">{{ name }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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
</script>

<style scoped>
.mini-history {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 2px;
  display: flex;
  flex-direction: column;
  gap: 6px;
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

.mini-turn {
  border: 1px solid var(--border-base);
  border-radius: 10px;
  padding: 6px 8px;
  cursor: pointer;
  transition: border-color .15s, background .15s;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.mini-turn:hover { border-color: var(--brand-c2); background: rgba(103, 232, 249, .05); }

.mini-input {
  font-size: 11px;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-left: 8px;
}
.mini-input::before { content: '你：'; color: var(--text-3); }

.mini-line { display: flex; align-items: center; gap: 6px; min-width: 0; }
.mini-summary {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mini-tool {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--brand-c2);
  border: 1px solid var(--border-base);
  border-radius: 4px;
  padding: 1px 5px;
  background: rgba(34, 211, 238, .06);
}
</style>
