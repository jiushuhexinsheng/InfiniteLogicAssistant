<template>
  <div class="console-memory">
    <!-- 记忆头部：刷新按钮和加载状态。Memory header: refresh button and loading state. -->
    <div class="mem-head">
      <UiButton variant="ghost" size="sm" @click="loadMemory">刷新</UiButton>
      <span v-if="loading" class="mem-loading">加载中…</span>
    </div>
    <UiErrorNote v-if="error" :error="error" />
    <div v-else-if="!(facts ?? []).length && !loading" class="console-empty">暂无记忆（任务完成后会自动提取）</div>
    <!-- 记忆列表：展示每条记忆的主题、时间、来源和内容，支持删除。Memory list: shows topic, time, source and content of each memory fact, with delete support. -->
    <UiCard v-for="f in (facts ?? [])" :key="f.topic" class="mem-item">
      <div class="mem-topic">
        {{ f.topic }}
        <span class="mem-ts">{{ f.ts }} · {{ f.source }}</span>
      </div>
      <div class="mem-content">{{ f.content }}</div>
      <UiButton variant="ghost" size="sm" hover="danger" @click="remove(f.topic)">删除</UiButton>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { api } from '../../api'
import { useAsync } from '../../composables/useAsync'
import { notify } from '../../composables/useToast'
import { formatError } from '../../errors'
import { UiButton, UiCard, UiErrorNote } from '../ui'

/** 记忆事实列表加载：统一错误捕获（替代原先只写 console.error、界面上完全看不到失败的写法）。
 *  Memory facts loading with unified error capture (replaces the previous version that only logged to console.error, leaving the failure invisible in the UI). */
const { data: facts, error, loading, run: loadMemory } = useAsync(async () => {
  const r = await api.getMemory()
  return r.facts || []
})

/**
 * 按主题删除一条记忆事实并刷新列表。
 * Delete a memory fact by topic and refresh the list.
 *
 * @param topic 记忆主题。Memory topic.
 */
async function remove(topic: string) {
  try {
    await api.deleteMemory(topic)
    notify.ok(`已删除记忆「${topic}」`)
    await loadMemory()
  } catch (e) {
    notify.err('删除记忆失败：' + formatError(e))
  }
}

onMounted(() => { loadMemory() })
</script>

<style scoped>
.console-memory { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; flex: 1; min-height: 0; overflow-y: auto;}
.mem-head { display: flex; align-items: center; gap: 10px; }
.mem-loading { font-size: 12px; color: var(--text-3); }
.console-empty { display: flex; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; }
.mem-item { display: flex; flex-direction: column; gap: 6px; }
.mem-topic { font-size: 13px; font-weight: 600; color: var(--brand-c2); }
.mem-ts { font-size: 11px; color: var(--text-3); font-weight: 400; margin-left: 8px; }
.mem-content { font-size: 12px; color: var(--text-2); }
</style>
