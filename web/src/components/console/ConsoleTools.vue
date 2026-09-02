<template>
  <div class="console-tools">
    <div v-if="loading" class="console-empty">加载中…</div>
    <div v-else-if="error" class="console-empty">加载失败：{{ error }}</div>
    <div v-else-if="!tools.length" class="console-empty">后端没有注册工具</div>
    <!-- 工具列表：展示每个工具的名称、描述，点击展开查看参数定义。Tool list: shows name and description of each tool, click to expand and view parameter definitions. -->
    <div v-else class="tool-cards">
      <UiCard v-for="t in tools" :key="t.function.name" class="tool-card" :padded="false">
        <div class="tool-head" @click="toggle(t.function.name)">
          <code class="tool-name">{{ t.function.name }}</code>
          <span class="tool-desc">{{ t.function.description }}</span>
          <UiIcon name="chevron-down" :size="12" class="tool-chev" :class="{ rot: open === t.function.name }" />
        </div>
        <div v-if="open === t.function.name" class="tool-params">
          <pre>{{ JSON.stringify(t.function.parameters, null, 2) }}</pre>
        </div>
      </UiCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import type { ToolSchema } from '../../types'
import { UiCard, UiIcon } from '../ui'

/** 后端注册的工具列表。List of tools registered in backend. */
const tools = ref<ToolSchema[]>([])
/** 加载状态标志。Loading state flag. */
const loading = ref(true)
/** 加载错误信息。Load error message. */
const error = ref('')
/** 当前展开的工具名称（用于折叠/展开切换）。Currently expanded tool name (for collapse/expand toggle). */
const open = ref('')

/** 切换工具详情的展开/折叠。Toggle tool details expand/collapse. */
function toggle(name: string) { open.value = open.value === name ? '' : name }

onMounted(async () => {
  try {
    const r = await api.getTools()
    if (r.ok) tools.value = r.tools
    else error.value = r.error || '未知错误'
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.console-tools { max-width: 720px; width: 100%; margin: 0 auto; flex: 1; min-height: 0; overflow-y: auto;}
.console-empty { display: flex; align-items: center; justify-content: center; color: var(--text-3); font-size: 13px; padding: 40px 0; }
.tool-cards { display: flex; flex-direction: column; gap: 10px; }
.tool-card { padding: 14px 16px; }
.tool-head { display: flex; align-items: center; gap: 12px; cursor: pointer; }
.tool-name { font-family: var(--font-mono); font-size: 13px; color: var(--brand-c2); background: rgba(103, 232, 249, .08); border: 1px solid var(--border-base); border-radius: 6px; padding: 2px 8px; }
.tool-desc { flex: 1; font-size: 12px; color: var(--text-2); }
.tool-chev { color: var(--text-3); transition: transform .15s; }
.tool-chev.rot { transform: rotate(180deg); }
.tool-params { margin-top: 10px; }
.tool-params pre { margin: 0; background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 8px; padding: 10px 12px; font-size: 11px; line-height: 1.6; color: #a5b4fc; overflow-x: auto; max-height: 260px; overflow-y: auto; }
</style>
