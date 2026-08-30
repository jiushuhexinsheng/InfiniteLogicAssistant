<template>
  <div class="console-schedule">
    <UiCard title="注册定时任务" class="sched-form">
      <div class="form-row">
        <UiInput v-model="cron" placeholder="cron 5段，如 0 9 * * *" class="cron-input" />
        <UiInput v-model="prompt" placeholder="到点执行的内容，如：查一下济南天气" />
        <UiButton variant="secondary" size="sm" :disabled="!cron || !prompt" @click="add">注册</UiButton>
      </div>
    </UiCard>

    <div v-if="!list.length && !loading" class="console-empty">暂无定时任务</div>
    <UiCard v-for="s in list" :key="s.id" class="sched-item">
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
import { api, type ScheduleItem } from '../../api'
import { UiButton, UiCard, UiInput } from '../ui'

const cron = ref('')
const prompt = ref('')
const list = ref<ScheduleItem[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.getSchedules()
    list.value = r.schedules || []
  } catch (e: any) {
    console.error('getSchedules', e)
  } finally {
    loading.value = false
  }
}

async function add() {
  if (!cron.value.trim() || !prompt.value.trim()) return
  try {
    await api.addSchedule(cron.value.trim(), prompt.value.trim())
    cron.value = ''
    prompt.value = ''
    await load()
  } catch (e: any) {
    console.error('addSchedule', e)
  }
}

async function remove(sid: string) {
  try {
    await api.deleteSchedule(sid)
    await load()
  } catch (e: any) {
    console.error('deleteSchedule', e)
  }
}

onMounted(load)
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
