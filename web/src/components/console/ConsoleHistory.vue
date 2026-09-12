<template>
  <div class="console-history">
    <!-- 操作栏：新建会话、切换归档/活跃视图、刷新列表。Action bar: create session, toggle archived/active view, refresh list. -->
    <div class="history-actions">
      <UiButton variant="primary" size="sm" @click="create">＋ 新建会话</UiButton>
      <UiButton variant="ghost" size="sm" @click="toggleArchived">{{ showArchived ? '← 返回会话' : '查看归档' }}</UiButton>
      <UiButton variant="ghost" size="sm" @click="loadSessions">刷新</UiButton>
      <span v-if="loading" class="hint">加载中…</span>
    </div>

    <UiErrorNote v-if="error" :error="error" />

    <!-- 会话列表：展示每条会话的名称、时间、消息数及操作按钮。Session list: displays name, time, message count and action buttons for each session. -->
    <div class="history-list">
      <UiCard v-for="c in (list ?? [])" :key="c.id" class="history-item" @click="open(c.id)">
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
      <p v-if="!(list ?? []).length && !loading" class="empty">
        {{ showArchived ? '暂无归档会话' : '暂无会话，点「新建会话」开始对话' }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../../api'
import type { SessionItem } from '../../types'
import { useAsync } from '../../composables/useAsync'
import { notify } from '../../composables/useToast'
import { formatError } from '../../errors'
import { UiButton, UiCard, UiErrorNote } from '../ui'
import { useConsole } from '../../composables/useConsole'
import { createNewSession, switchSession } from '../../composables/assistant/store'

/** 当前控制台活跃标签页。Current console active tab. */
const { activeTab } = useConsole()
/** 是否显示已归档会话。Whether to show archived sessions. */
const showArchived = ref(false)

/** 会话列表加载：统一错误捕获（替代原先 catch 后完全静默的写法）。
 *  Session list loading with unified error capture (replaces the previous fully-silent catch). */
const { data: list, error, loading, run: loadSessions } = useAsync(async () => {
  const r = await api.listSessions(showArchived.value || undefined)
  return r.sessions
})

/**
 * 切换归档/活跃视图并重新加载。
 * Toggle the archived/active view and reload.
 */
function toggleArchived() {
  showArchived.value = !showArchived.value
  loadSessions()
}

/**
 * 执行一次会话操作并统一反馈（成功提示 + 刷新列表 / 失败提示）。
 * Run a session operation with unified feedback (success notice + list refresh / failure notice).
 *
 * @param label 操作名（用于文案）。Operation name (for the message).
 * @param fn 实际操作。The actual operation.
 */
async function act(label: string, fn: () => Promise<unknown>) {
  try {
    await fn()
    notify.ok(`${label}成功`)
    await loadSessions()
  } catch (e) {
    notify.err(`${label}失败：` + formatError(e))
  }
}

/** 新建会话 → 清空当前对话，切到对话视图续写新会话。Create a new session → clear the current conversation, switch to the conversation view for the new session. */
async function create() {
  try {
    const r = await api.createSession()
    createNewSession(r.session.id)
    activeTab.value = 'conv'
    notify.ok('已新建会话')
  } catch (e) {
    notify.err('新建会话失败：' + formatError(e))
  }
}

/** 点击会话 = 切换：加载其历史消息填充对话视图，后续对话续接该会话。Click a session = switch: load its history into the conversation view and continue from that session. */
async function open(id: string) {
  try {
    const r = await api.getHistoryDetail(id)
    const msgs = (r.conversation.messages || []).map(m => ({ role: m.role, content: m.content }))
    switchSession(id, msgs)
    activeTab.value = 'conv'
  } catch (e) {
    notify.err('打开会话失败：' + formatError(e))
  }
}

/**
 * 清除上下文：清空消息，会话保留。
 * Clear the context: clear messages while keeping the session.
 *
 * @param c 会话条目。The session item.
 */
async function clearCtx(c: SessionItem) {
  if (!window.confirm(`清除「${c.name}」的上下文？会话记录保留。`)) return
  await act('清除上下文', () => api.clearSession(c.id))
}

/**
 * 切换会话的归档状态。
 * Toggle the archived state of a session.
 *
 * @param c 会话条目。The session item.
 */
async function toggleArchive(c: SessionItem) {
  await act(c.archived ? '取消归档' : '归档', () => api.archiveSession(c.id, !c.archived))
}

/**
 * 删除会话（不可恢复）。
 * Delete a session (irreversible).
 *
 * @param id 会话 id。Session id.
 */
async function remove(id: string) {
  await act('删除会话', () => api.deleteSession(id))
}

/**
 * 重命名会话。
 * Rename a session.
 *
 * @param c 会话条目。The session item.
 */
async function rename(c: SessionItem) {
  const name = window.prompt('重命名会话', c.name)
  if (!name || name === c.name) return
  await act('重命名', () => api.renameSession(c.id, name.trim()))
}

/**
 * 格式化时间戳：将 ISO 格式转为 "YYYY-MM-DD HH:mm:ss"。
 * Format a timestamp: convert ISO format to "YYYY-MM-DD HH:mm:ss".
 *
 * @param ts ISO 时间戳。The ISO timestamp.
 * @returns 格式化后的时间串。The formatted timestamp.
 */
function fmt(ts: string) { return ts ? ts.replace('T', ' ').slice(0, 19) : '' }

onMounted(() => { loadSessions() })
</script>

<style scoped>
.console-history { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; flex: 1; min-height: 0; overflow-y: auto;}
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
