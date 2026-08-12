<template>
  <div class="console-memory">
    <div class="mem-head">
      <button class="mini-btn" @click="load">刷新</button>
      <span v-if="loading" class="mem-loading">加载中…</span>
    </div>
    <div v-if="!facts.length && !loading" class="console-empty">暂无记忆（任务完成后会自动提取）</div>
    <div v-for="f in facts" :key="f.topic" class="card mem-item">
      <div class="mem-topic">
        {{ f.topic }}
        <span class="mem-ts">{{ f.ts }} · {{ f.source }}</span>
      </div>
      <div class="mem-content">{{ f.content }}</div>
      <button class="mini-btn danger" @click="remove(f.topic)">删除</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type MemoryFact } from '../../api'

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
.mini-btn {
  background: none;
  border: 1px solid var(--border-base);
  color: var(--text-2);
  font-size: 12px;
  padding: 5px 14px;
  border-radius: 999px;
  cursor: pointer;
}
.mini-btn:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.mini-btn.danger:hover { color: #f87171; border-color: #f87171; }
.mem-loading { font-size: 12px; color: var(--text-3); }
.console-empty { display: flex; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; }
.mem-item { position: relative; padding-right: 70px; }
.mem-topic { font-size: 13px; font-weight: 600; color: var(--brand-c2); }
.mem-ts { font-size: 11px; color: var(--text-3); font-weight: 400; margin-left: 8px; }
.mem-content { font-size: 12px; color: var(--text-2); margin-top: 4px; }
.mem-item .mini-btn { position: absolute; right: 14px; top: 12px; }
</style>
