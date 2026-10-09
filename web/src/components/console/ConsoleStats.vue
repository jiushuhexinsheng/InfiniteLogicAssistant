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

    <!-- 云端上传成本（audit 的 audio-upload via= 三前缀计数 + 近 7 日趋势；后端只回计数与日期）。
         Cloud upload cost (audio-upload via= counts + 7-day trend; the backend returns counts and dates only). -->
    <UiCard class="upload-stats">
      <h3 class="upload-title">云端音频上传（成本口径）</h3>
      <div class="stats-grid">
        <div v-for="c in uploadCards" :key="c.lbl" class="stat">
          <div class="num">{{ c.num }}</div>
          <div class="lbl">{{ c.lbl }}</div>
        </div>
      </div>
      <div v-if="uploadStats" class="trend">
        <div v-for="d in uploadStats.days" :key="d.date" class="trend-bar"
             :title="`${d.date}：${d.wake + d.transcribe + d['call-segment']} 次`"
             :style="{ height: trendHeight(d) }"></div>
      </div>
      <p class="hint">未命中唤醒词的人声段不上传（本地 KWS 闸门），不计入本口径。</p>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAssistant } from '../../composables/useAssistant'
import { UiCard } from '../ui'

/** 当前助手实例。Current assistant instance. */
const asst = useAssistant()

/** 上传统计数据（挂载时拉取；失败为 null → 卡片显示 —）。Upload stats (fetched on
 *  mount; null on failure → cards show —). */
const uploadStats = ref<Awaited<ReturnType<typeof api.getUploadStats>> | null>(null)

onMounted(async () => {
  try {
    uploadStats.value = await api.getUploadStats()
  } catch { /* 降级：上传卡片显示 —。Degrade: upload cards show —. */ }
})

/** 上传统计卡片（三前缀 + 合计；加载失败全部 —）。Upload stat cards (three vias +
 *  total; all — when the fetch failed). */
const uploadCards = computed(() => {
  const s = uploadStats.value
  if (!s) return [
    { num: '—', lbl: '唤醒上传' }, { num: '—', lbl: '转写上传' },
    { num: '—', lbl: '通话上传' }, { num: '—', lbl: '上传合计' },
  ]
  return [
    { num: s.by_via.wake, lbl: '唤醒上传' },
    { num: s.by_via.transcribe, lbl: '转写上传' },
    { num: s.by_via['call-segment'], lbl: '通话上传' },
    { num: s.total, lbl: '上传合计' },
  ]
})

/** 趋势柱高（按日合计相对窗口最大值；全零时给基础高度保形）。
 *  Bar height (daily total vs. the window max; a floor keeps shape when all zero). */
function trendHeight(d: { wake: number; transcribe: number; 'call-segment': number }): string {
  const s = uploadStats.value
  if (!s) return '2px'
  const max = Math.max(1, ...s.days.map((x) => x.wake + x.transcribe + x['call-segment']))
  const n = d.wake + d.transcribe + d['call-segment']
  return `${Math.round((n / max) * 36) + 2}px`
}

/** 统计数据：消息数、用户/助手消息数、工具调用数和工具总耗时。Statistics: message count, user/assistant message count, tool call count and total tool duration. */
const stats = computed(() => {
  const msgs = asst.messages.value
  let toolCount = 0
  let toolDuration = 0
  for (const m of msgs) {
    // 工具统计走 tool 块（块协议是事实源；原 toolCalls 字段已随兼容链删除）。
    // Tool stats read tool blocks (the block protocol is the source of truth; the
    // legacy toolCalls field went away with the compat chain).
    for (const b of m.blocks || []) {
      if (b.type !== 'tool') continue
      toolCount++
      const ms = (b.payload as { duration_ms?: number }).duration_ms
      if (ms != null) toolDuration += ms
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
.upload-stats { margin-top: 18px; }
.upload-title { font-size: 13px; font-weight: 600; color: var(--text-2); margin: 0 0 10px; }
.trend { display: flex; align-items: flex-end; gap: 6px; height: 44px; margin-top: 14px; }
.trend-bar { flex: 1; min-height: 2px; background: var(--brand-c2); opacity: .75; border-radius: 2px 2px 0 0; }
</style>
