<template>
  <div class="console-stats">
    <div class="stats-grid">
      <div class="card stat">
        <div class="num">{{ stats.messageCount }}</div>
        <div class="lbl">消息总数</div>
      </div>
      <div class="card stat">
        <div class="num">{{ stats.userCount }}</div>
        <div class="lbl">你的提问</div>
      </div>
      <div class="card stat">
        <div class="num">{{ stats.assistantCount }}</div>
        <div class="lbl">小逻回复</div>
      </div>
      <div class="card stat">
        <div class="num">{{ stats.toolCount }}</div>
        <div class="lbl">工具调用</div>
      </div>
      <div class="card stat">
        <div class="num">{{ stats.toolDuration }}s</div>
        <div class="lbl">工具总耗时</div>
      </div>
      <div class="card stat">
        <div class="num">{{ tokenTotal ?? '—' }}</div>
        <div class="lbl">token 用量</div>
      </div>
    </div>
    <p class="hint">
      会话内统计，清空对话后归零。token 来自后端 SSE usage 透传（逐轮累计），提供方不回传时显示 —。
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAssistant } from '../../composables/useAssistant'

const asst = useAssistant()

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

const tokenTotal = computed<number | null>(() => {
  const u = asst.tokenUsage.value
  return u.total_tokens != null ? u.total_tokens : null
})
</script>

<style scoped>
.console-stats { max-width: 720px; width: 100%; margin: 0 auto; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}
.stat { text-align: center; padding: 18px 12px; }
.num { font-size: 26px; font-weight: 700; color: var(--brand-c2); }
.lbl { font-size: 12px; color: var(--text-3); margin-top: 4px; }
.hint { font-size: 11px; color: var(--text-3); margin-top: 14px; line-height: 1.6; }
</style>
