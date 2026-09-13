<template>
  <div class="console-library">
    <!-- 任务库头部：说明与刷新。Task-library header: description and refresh. -->
    <div class="lib-head">
      <UiButton variant="ghost" size="sm" @click="loadTasks">刷新</UiButton>
      <span v-if="loading" class="lib-loading">加载中…</span>
    </div>
    <UiErrorNote v-if="error" :error="error" />
    <div v-else-if="!(tasks ?? []).length && !loading" class="console-empty">
      暂无任务存档（任务模式下完成一个任务并确认「完成了」后会出现在这里）
    </div>
    <!-- 任务列表：展开可看参数与步骤（只读，不支持回放）。Task list: expand to view params and steps (read-only, no replay). -->
    <UiCard v-for="t in (tasks ?? [])" :key="t.id" class="lib-item">
      <div class="lib-row" @click="toggle(t.id)">
        <span class="lib-goal">{{ t.goal }}</span>
        <span class="lib-time">{{ fmt(t.created) }}</span>
        <span class="lib-count">{{ Object.keys(t.params || {}).length }} 个参数</span>
        <UiButton variant="ghost" size="sm" hover="danger" @click.stop="remove(t.id)">删除</UiButton>
      </div>
      <div v-if="open === t.id" class="lib-detail">
        <div class="lib-sec-title">参数</div>
        <pre>{{ JSON.stringify(t.params, null, 2) }}</pre>
        <div class="lib-sec-title">步骤（只读，不支持回放）</div>
        <pre>{{ JSON.stringify(t.steps, null, 2) }}</pre>
      </div>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAsync } from '../../composables/useAsync'
import { notify } from '../../composables/useToast'
import { formatError } from '../../errors'
import { UiButton, UiCard, UiErrorNote } from '../ui'

/** 任务库存档加载：统一错误捕获。Task-library loading with unified error capture. */
const { data: tasks, error, loading, run: loadTasks } = useAsync(async () => {
  const r = await api.listLibrary()
  return r.tasks || []
})

/** 当前展开的任务 id。Currently expanded task id. */
const open = ref<number | null>(null)

/**
 * 展开 / 收起某条任务的详情。
 * Expand / collapse one task's details.
 *
 * @param id 任务 id。The task id.
 */
function toggle(id: number) {
  open.value = open.value === id ? null : id
}

/**
 * 删除一条任务存档并刷新。
 * Delete one archived task and refresh the list.
 *
 * @param id 任务 id。The task id.
 */
async function remove(id: number) {
  try {
    await api.deleteLibraryTask(id)
    notify.ok('已删除任务存档')
    await loadTasks()
  } catch (e) {
    notify.err('删除任务失败：' + formatError(e))
  }
}

/**
 * 格式化时间戳。
 * Format a timestamp.
 *
 * @param ts ISO 时间戳。The ISO timestamp.
 * @returns "YYYY-MM-DD HH:mm"。The formatted timestamp.
 */
function fmt(ts: string) {
  return ts ? ts.replace('T', ' ').slice(0, 16) : ''
}

onMounted(() => { loadTasks() })
</script>

<style scoped>
.console-library { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; flex: 1; min-height: 0; overflow-y: auto; }
.lib-head { display: flex; align-items: center; gap: 10px; }
.lib-loading { font-size: 12px; color: var(--text-3); }
.console-empty { display: flex; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; text-align: center; }
.lib-item { padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }
.lib-row { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 12px; color: var(--text-3); }
.lib-goal { font-size: 14px; font-weight: 600; color: var(--text-1); flex: 1; }
.lib-time { white-space: nowrap; }
.lib-count { white-space: nowrap; }
.lib-detail { display: flex; flex-direction: column; gap: 4px; border-top: 1px dashed var(--border-soft); padding-top: 8px; }
.lib-sec-title { font-size: var(--fs-2xs); color: var(--text-3); }
.lib-detail pre { margin: 0 0 6px; background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 8px; padding: 8px 10px; font-size: 11px; line-height: 1.6; color: var(--text-2); overflow-x: auto; max-height: 220px; overflow-y: auto; }
</style>
