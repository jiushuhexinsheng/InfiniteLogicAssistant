<template>
  <div class="console-env">
    <div class="env-head">
      <button class="mini-btn" @click="load">刷新</button>
      <span v-if="loading" class="env-loading">加载中…</span>
    </div>
    <pre v-if="content" class="env-pre">{{ content }}</pre>
    <div v-else-if="!loading" class="console-empty">暂无环境快照（首次运行会自动生成）</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api'

const content = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.getEnv()
    content.value = r.content
  } catch (e: any) {
    content.value = '加载失败: ' + (e?.message || String(e))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.console-env { max-width: 860px; width: 100%; margin: 0 auto; }
.env-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
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
.env-loading { font-size: 12px; color: var(--text-3); }
.env-pre {
  background: #0b1120;
  border: 1px solid var(--border-base);
  border-radius: 10px;
  padding: 14px 16px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-1);
  overflow: auto;
  max-height: 60vh;
  white-space: pre-wrap;
  word-break: break-all;
}
.console-empty {
  display: flex;
  justify-content: center;
  color: var(--text-3);
  font-size: 13px;
  padding: 40px 0;
}
</style>
