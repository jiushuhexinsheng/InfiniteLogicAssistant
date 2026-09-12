<template>
  <div class="console-env">
    <!-- 环境快照头部：刷新按钮和加载状态。Environment snapshot header: refresh button and loading state. -->
    <div class="env-head">
      <UiButton variant="ghost" size="sm" @click="loadEnv">刷新</UiButton>
      <span v-if="loading" class="env-loading">加载中…</span>
    </div>
    <UiErrorNote v-if="error" :error="error" />
    <!-- 环境快照内容区域：有内容时显示 <pre>，否则显示空提示。Environment snapshot content: shows <pre> when content exists, otherwise an empty hint. -->
    <pre v-else-if="content" class="env-pre">{{ content }}</pre>
    <div v-else-if="!loading" class="console-empty">暂无环境快照（首次运行会自动生成）</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { api } from '../../api'
import { useAsync } from '../../composables/useAsync'
import { UiButton, UiErrorNote } from '../ui'

/** 环境快照加载：统一错误捕获与文案（替代原先把 '加载失败: ' 拼进 content 再渲染到 <pre> 的写法）。
 *  Environment snapshot loading with unified error capture (replaces baking '加载失败: ' into content and rendering it inside <pre>). */
const { data: content, error, loading, run: loadEnv } = useAsync(async () => {
  const r = await api.getEnv()
  return r.content
})

onMounted(() => { loadEnv() })
</script>

<style scoped>
.console-env { max-width: 860px; width: 100%; margin: 0 auto; flex: 1; min-height: 0; overflow-y: auto;}
.env-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.env-loading { font-size: 12px; color: var(--text-3); }
.env-pre { background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 10px; padding: 14px 16px; font-size: 12px; line-height: 1.7; color: var(--text-1); overflow: auto; max-height: 60vh; white-space: pre-wrap; word-break: break-all; }
.console-empty { display: flex; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; }
</style>
