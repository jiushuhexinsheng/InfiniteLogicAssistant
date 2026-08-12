<template>
  <div class="console-schedule">
    <div class="card sched-form">
      <div class="card-title">注册定时任务</div>
      <div class="form-row">
        <input v-model="cron" placeholder="cron 5段，如 0 9 * * *" />
        <input v-model="prompt" placeholder="到点执行的内容，如：查一下济南天气" />
        <button class="mini-btn" :disabled="!cron || !prompt" @click="add">注册</button>
      </div>
    </div>

    <div v-if="!list.length && !loading" class="console-empty">暂无定时任务</div>
    <div v-for="s in list" :key="s.id" class="card sched-item">
      <div class="sched-line">
        <code>{{ s.cron }}</code>
        <span class="sched-prompt">{{ s.prompt }}</span>
      </div>
      <button class="mini-btn danger" @click="remove(s.id)">删除</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type ScheduleItem } from '../../api'

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
.console-schedule { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; gap: 8px; }
.form-row input {
  flex: 1;
  background: #0b1120;
  border: 1px solid var(--border-base);
  border-radius: 8px;
  color: var(--text-1);
  padding: 7px 10px;
  font-size: 13px;
}
.form-row input:first-child { max-width: 140px; font-family: ui-monospace, Consolas, monospace; }
.mini-btn {
  background: none;
  border: 1px solid var(--border-base);
  color: var(--text-2);
  font-size: 12px;
  padding: 5px 14px;
  border-radius: 999px;
  cursor: pointer;
  white-space: nowrap;
}
.mini-btn:hover:not(:disabled) { color: var(--brand-c2); border-color: var(--brand-c2); }
.mini-btn:disabled { opacity: .5; cursor: default; }
.mini-btn.danger:hover { color: #f87171; border-color: #f87171; }
.console-empty { display: flex; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; }
.sched-item { display: flex; align-items: center; gap: 12px; }
.sched-line { flex: 1; display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.sched-line code { color: var(--brand-c2); font-family: ui-monospace, Consolas, monospace; font-size: 12px; }
.sched-prompt { color: var(--text-2); font-size: 13px; }
</style>
