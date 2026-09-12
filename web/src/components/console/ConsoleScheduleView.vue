<template>
  <div class="console-schedule">
    <!-- 定时任务注册表单：输入 cron 表达式和执行内容。Schedule registration form: input cron expression and prompt content. -->
    <UiCard title="注册定时任务" class="sched-form">
      <div class="form-row">
        <UiInput v-model="cron" placeholder="cron 5段，如 0 9 * * *" class="cron-input" />
        <UiInput v-model="prompt" placeholder="到点执行的内容，如：查一下济南天气" />
        <UiButton variant="secondary" size="sm" :disabled="!cron || !prompt" @click="add">注册</UiButton>
      </div>
    </UiCard>

    <UiErrorNote v-if="error" :error="error" />
    <!-- 定时任务列表：展示每条任务的 cron 表达式和执行内容，支持删除。Schedule list: shows cron expression and prompt for each task, with delete support. -->
    <div v-else-if="!(list ?? []).length && !loading" class="console-empty">暂无定时任务</div>
    <UiCard v-for="s in (list ?? [])" :key="s.id" class="sched-item">
      <div class="sched-line">
        <code>{{ s.cron }}</code>
        <span class="sched-prompt">{{ s.prompt }}</span>
      </div>
      <UiButton variant="ghost" size="sm" hover="danger" @click="remove(s.id)">删除</UiButton>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAsync } from '../../composables/useAsync'
import { notify } from '../../composables/useToast'
import { formatError } from '../../errors'
import { UiButton, UiCard, UiErrorNote, UiInput } from '../ui'

/** cron 表达式输入。Cron expression input. */
const cron = ref('')
/** 定时执行的 prompt 内容。Scheduled prompt content. */
const prompt = ref('')

/** 定时任务列表加载：统一错误捕获（替代原先只写 console.error、界面上完全看不到失败的写法）。
 *  Schedule list loading with unified error capture (replaces the previous version that only logged to console.error, leaving the failure invisible in the UI). */
const { data: list, error, loading, run: loadSchedules } = useAsync(async () => {
  const r = await api.getSchedules()
  return r.schedules || []
})

/**
 * 注册新的定时任务并刷新列表。
 * Register a new scheduled task and refresh the list.
 */
async function add() {
  if (!cron.value.trim() || !prompt.value.trim()) return
  try {
    await api.addSchedule(cron.value.trim(), prompt.value.trim())
    cron.value = ''
    prompt.value = ''
    notify.ok('已注册定时任务')
    await loadSchedules()
  } catch (e) {
    notify.err('注册定时任务失败：' + formatError(e))
  }
}

/**
 * 删除定时任务并刷新列表。
 * Delete a scheduled task and refresh the list.
 *
 * @param sid 定时任务 id。Schedule id.
 */
async function remove(sid: string) {
  try {
    await api.deleteSchedule(sid)
    notify.ok('已取消定时任务')
    await loadSchedules()
  } catch (e) {
    notify.err('取消定时任务失败：' + formatError(e))
  }
}

onMounted(() => { loadSchedules() })
</script>

<style scoped>
.console-schedule { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; flex: 1; min-height: 0; overflow-y: auto;}
.sched-form { display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; gap: 8px; align-items: center; }
.cron-input { max-width: 150px; font-family: var(--font-mono); }
.console-empty { display: flex; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; }
.sched-item { display: flex; align-items: center; gap: 12px; padding: 12px 14px; }
.sched-line { flex: 1; display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.sched-line code { color: var(--brand-c2); font-family: var(--font-mono); font-size: 12px; }
.sched-prompt { color: var(--text-2); font-size: 13px; }
</style>
