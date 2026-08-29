<template>
  <div class="console-memory">
    <div class="mem-head">
      <UiButton variant="ghost" size="sm" @click="load">刷新</UiButton>
      <span v-if="loading" class="mem-loading">加载中…</span>
    </div>
    <div v-if="!facts.length && !loading" class="console-empty">暂无记忆（任务完成后会自动提取）</div>
    <UiCard v-for="f in facts" :key="f.topic" class="mem-item">
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
import { onMounted, ref } from 'vue'
import { api, type MemoryFact } from '../../api'
import { UiButton, UiCard } from '../ui'

const facts = ref<MemoryFact[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.getMemory()
    facts.value = r.facts || []
  } catch (e: any) {
    facts.value = []
    console.error('getMemory', e)
  } finally {
    loading.value = false
  }
}

async function remove(topic: string) {
  try {
    await api.deleteMemory(topic)
    await load()
  } catch (e: any) {
    console.error('deleteMemory', e)
  }
}

onMounted(load)
</script>

<style scoped>
.console-memory { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
.mem-head { display: flex; align-items: center; gap: 10px; }
.mem-loading { font-size: 12px; color: var(--text-3); }
.console-empty { display: flex; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; }
.mem-item { display: flex; flex-direction: column; gap: 6px; }
.mem-topic { font-size: 13px; font-weight: 600; color: var(--brand-c2); }
.mem-ts { font-size: 11px; color: var(--text-3); font-weight: 400; margin-left: 8px; }
.mem-content { font-size: 12px; color: var(--text-2); }
</style>
