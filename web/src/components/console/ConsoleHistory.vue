<template>
  <div class="console-history">
    <div class="history-actions">
      <UiButton variant="primary" size="sm" @click="create">＋ 新建会话</UiButton>
      <UiButton variant="ghost" size="sm" @click="toggleArchived">{{ showArchived ? '← 返回会话' : '查看归档' }}</UiButton>
      <UiButton variant="ghost" size="sm" @click="load">刷新</UiButton>
      <span v-if="loading" class="hint">加载中…</span>
    </div>

    <div class="history-list">
      <UiCard v-for="c in list" :key="c.id" class="history-item" @click="open(c.id)">
        <div class="hi-row">
          <span class="hi-name">{{ c.name || '（未命名会话）' }}</span>
          <span class="hi-time">{{ fmt(c.updated) }}</span>
          <span class="hi-count">{{ c.message_count }} 条</span>
          <span class="hi-ops">
            <UiButton variant="ghost" size="sm" @click.stop="clearCtx(c)">清空</UiButton>
            <UiButton variant="ghost" size="sm" @click.stop="toggleArchive(c)">{{ c.archived ? '取消归档' : '归档' }}</UiButton>
            <UiButton variant="ghost" size="sm" @click.stop="rename(c)">重命名</UiButton>
            <UiButton variant="ghost" size="sm" hover="danger" @click.stop="remove(c.id)">删除</UiButton>
          </span>
        </div>
        <div class="hi-summary">{{ c.summary || '（暂无内容）' }}</div>
      </UiCard>
      <p v-if="!list.length && !loading" class="empty">
        {{ showArchived ? '暂无归档会话' : '暂无会话，点「新建会话」开始对话' }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api'
import type { SessionItem } from '../../types'
import { UiButton, UiCard } from '../ui'
import { useConsole } from '../../composables/useConsole'
import { createNewSession, switchSession } from '../../composables/assistant/store'

const { activeTab } = useConsole()
const list = ref<SessionItem[]>([])
const showArchived = ref(false)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.listSessions(showArchived.value || undefined)
    list.value = r.sessions
  } catch { /* 后端未就绪时静默 */ } finally {
    loading.value = false
  }
}

function toggleArchived() {
  showArchived.value = !showArchived.value
  load()
}

/** 新建会话 → 清空当前对话，切到对话视图续写新会话 */
async function create() {
  try {
    const r = await api.createSession()
    createNewSession(r.session.id)
    activeTab.value = 'conv'
  } catch { /* ignore */ }
}

/** 点击会话 = 切换：加载其历史消息填充对话视图，后续对话续接该会话 */
async function open(id: string) {
  try {
    const r = await api.getHistoryDetail(id)
    const msgs = (r.conversation.messages || []).map(m => ({ role: m.role, content: m.content }))
    switchSession(id, msgs)
    activeTab.value = 'conv'
  } catch { /* ignore */ }
}

/** 清除上下文：清空消息，会话保留 */
async function clearCtx(c: SessionItem) {
  if (!window.confirm(`清除「${c.name}」的上下文？会话记录保留。`)) return
  try {
    await api.clearSession(c.id)
    await load()
  } catch { /* ignore */ }
}

async function toggleArchive(c: SessionItem) {
  try {
    await api.archiveSession(c.id, !c.archived)
    await load()
  } catch { /* ignore */ }
}

async function remove(id: string) {
  try {
    await api.deleteSession(id)
    await load()
  } catch { /* ignore */ }
}

async function rename(c: SessionItem) {
  const name = window.prompt('重命名会话', c.name)
  if (!name || name === c.name) return
  try {
    await api.renameSession(c.id, name.trim())
    await load()
  } catch { /* ignore */ }
}

function fmt(ts: string) { return ts ? ts.replace('T', ' ').slice(0, 19) : '' }

onMounted(load)
</script>

<style scoped>
.console-history { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }
.history-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.hint { font-size: 12px; color: var(--text-3); }
.history-list { display: flex; flex-direction: column; gap: 10px; }
.history-item { padding: 12px 14px; cursor: pointer; display: flex; flex-direction: column; gap: 6px; }
.history-item:hover { border-color: var(--brand-c2); }
.hi-row { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-3); flex-wrap: wrap; }
.hi-name { font-size: 14px; font-weight: 600; color: var(--text-1); }
.hi-ops { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; }
.hi-count { white-space: nowrap; }
.hi-summary { font-size: 13px; color: var(--text-2); }
.empty { text-align: center; color: var(--text-3); font-size: 13px; padding: 30px 0; }
</style>
