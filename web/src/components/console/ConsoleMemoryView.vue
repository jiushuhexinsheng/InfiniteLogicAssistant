<template>
  <ConsolePane stack :gap="10">
    <!-- 记忆头部：刷新按钮和加载状态。Memory header: refresh button and loading state. -->
    <div class="mem-head">
      <UiButton variant="ghost" size="sm" @click="loadMemory">刷新</UiButton>
      <span v-if="loading" class="mem-loading">加载中…</span>
    </div>
    <UiErrorNote v-if="error" :error="error" />
    <UiEmpty v-else-if="!(facts ?? []).length && !loading" text="暂无记忆（任务完成后会自动提取）" />
    <!-- 记忆列表：展示每条记忆的主题、时间、来源和内容，支持删除。Memory list: shows topic, time, source and content of each memory fact, with delete support. -->
    <UiCard v-for="f in (facts ?? [])" :key="f.topic" class="mem-item">
      <div class="mem-topic">
        {{ f.topic }}
        <span class="mem-ts">{{ f.ts }} · {{ f.source }}</span>
      </div>
      <div class="mem-content">{{ f.content }}</div>
      <UiButton variant="ghost" size="sm" hover="danger" @click="remove(f.topic)">删除</UiButton>
    </UiCard>
  </ConsolePane>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { api } from '../../api'
import { useAsync } from '../../composables/useAsync'
import { notify } from '../../composables/useToast'
import { formatError } from '../../errors'
import { UiButton, UiCard, UiEmpty, UiErrorNote } from '../ui'
import ConsolePane from './ConsolePane.vue'

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
.mem-head { display: flex; align-items: center; gap: var(--sp-q10); }
.mem-loading { font-size: var(--fs-xs); color: var(--text-3); }
.mem-item { display: flex; flex-direction: column; gap: var(--sp-q6); }
.mem-topic { font-size: 13px; font-weight: 600; color: var(--brand-c2); }
.mem-ts { font-size: var(--fs-2xs); color: var(--text-3); font-weight: 400; margin-left: var(--sp-2); }
.mem-content { font-size: var(--fs-xs); color: var(--text-2); }
</style>
