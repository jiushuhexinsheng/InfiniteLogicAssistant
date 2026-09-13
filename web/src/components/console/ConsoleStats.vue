<template>
  <div class="console-stats">
    <!-- 统计卡片网格：展示消息总数、提问数、回复数、工具调用数等。Stats card grid: shows total messages, user questions, assistant replies, tool call count, etc. -->
    <div class="stats-grid">
      <UiCard v-for="s in statCards" :key="s.lbl" class="stat">
        <div class="num">{{ s.num }}</div>
        <div class="lbl">{{ s.lbl }}</div>
      </UiCard>
    </div>
    <p class="hint">会话内统计，清空对话后归零。token 来自后端 SSE usage 透传（逐轮累计），提供方不回传时显示 —。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAssistant } from '../../composables/useAssistant'
import { UiCard } from '../ui'

/** 当前助手实例。Current assistant instance. */
const asst = useAssistant()

/** 统计数据：消息数、用户/助手消息数、工具调用数和工具总耗时。Statistics: message count, user/assistant message count, tool call count and total tool duration. */
const stats = computed(() => {
  const msgs = asst.messages.value
  let toolCount = 0
  let toolDuration = 0
  for (const m of msgs) {
    for (const tc of m.toolCalls || []) {
      toolCount++
      if (tc.durationMs != null) toolDuration += tc.durationMs
    }
  }
  return {
    messageCount: msgs.length,
    userCount: msgs.filter(m => m.role === 'user').length,
    assistantCount: msgs.filter(m => m.role === 'assistant').length,
    toolCount,
    toolDuration: (toolDuration / 1000).toFixed(1),
  }
})

/** Token 总用量（来自后端 SSE usage 透传，逐轮累计）。Total token usage (from backend SSE usage passthrough, accumulated per round). */
const tokenTotal = computed<number | null>(() => {
  const u = asst.tokenUsage.value
  return u.total_tokens != null ? u.total_tokens : null
})

/** 统计卡片数据数组（数字 + 标签）。Stats cards data array (number + label). */
const statCards = computed(() => [
  { num: stats.value.messageCount, lbl: '消息总数' },
  { num: stats.value.userCount, lbl: '你的提问' },
  { num: stats.value.assistantCount, lbl: '衍衡回复' },
  { num: stats.value.toolCount, lbl: '工具调用' },
  { num: stats.value.toolDuration + 's', lbl: '工具总耗时' },
  { num: tokenTotal.value ?? '—', lbl: 'token 用量' },
])
</script>

<style scoped>
.console-stats { max-width: 720px; width: 100%; margin: 0 auto; flex: 1; min-height: 0; overflow-y: auto;}
.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.stat { text-align: center; padding: 18px 12px; }
.num { font-size: 26px; font-weight: 700; color: var(--brand-c2); }
.lbl { font-size: 12px; color: var(--text-3); margin-top: 4px; }
.hint { font-size: 11px; color: var(--text-3); margin-top: 14px; line-height: 1.6; }
</style>
