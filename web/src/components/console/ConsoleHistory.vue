<template>
  <div class="console-history">
    <div class="history-actions">
      <button class="mini-btn" @click="load">刷新</button>
      <span v-if="loading" class="hint">加载中…</span>
    </div>

    <!-- 列表 -->
    <div v-if="!selected" class="history-list">
      <div v-for="c in list" :key="c.id" class="card history-item" @click="open(c.id)">
        <div class="hi-row">
          <span class="hi-time">{{ fmt(c.updated) }}</span>
          <span class="hi-status" :class="c.status">{{ statusLabel(c.status) }}</span>
          <span class="hi-count">{{ c.message_count }} 条</span>
        </div>
        <div class="hi-summary">{{ c.summary || '（无摘要）' }}</div>
        <button class="mini-btn danger" @click.stop="remove(c.id)">删除</button>
      </div>
      <p v-if="!list.length && !loading" class="empty">暂无历史记录</p>
    </div>

    <!-- 详情 -->
    <div v-else class="history-detail">
      <button class="mini-btn" @click="selected = null">← 返回列表</button>
      <div class="hi-title">{{ selected.summary || selected.id }}</div>
      <div class="hi-meta">{{ fmt(selected.created) }} · {{ statusLabel(selected.status) }} · {{ selected.messages.length }} 条消息</div>
      <div class="msg-list">
        <div v-for="(m, i) in selected.messages" :key="i" class="msg" :class="m.role">
          <span class="msg-role">{{ roleLabel(m.role) }}</span>
          <div class="msg-content">{{ m.content }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, type HistoryConversation, type HistoryConversationDetail } from '../../api'

const list = ref<HistoryConversation[]>([])
const selected = ref<HistoryConversationDetail | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.getHistory()
    list.value = r.conversations
  } catch { /* 后端未就绪时静默 */ } finally {
    loading.value = false
  }
}

async function open(id: string) {
  try {
    const r = await api.getHistoryDetail(id)
    selected.value = r.conversation
  } catch { /* ignore */ }
}

async function remove(id: string) {
  try {
    await api.deleteHistory(id)
    if (selected.value?.id === id) selected.value = null
    await load()
  } catch { /* ignore */ }
}

function fmt(ts: string) { return ts ? ts.replace('T', ' ').slice(0, 19) : '' }
function statusLabel(s: string) {
  return ({ done: '完成', failed: '失败', stopped: '已停止', cancelled: '已取消',
            idle: '空闲', understanding: '理解中', executing: '执行中' } as Record<string, string>)[s] || s || '—'
}
function roleLabel(r: string) {
  return ({ user: '用户', assistant: '小逻', tool: '🔧 工具', system: '系统' } as Record<string, string>)[r] || r
}

onMounted(load)
</script>

<style scoped>
.console-history { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }
.history-actions { display: flex; align-items: center; gap: 8px; }
.hint { font-size: 12px; color: var(--text-3); }

.mini-btn {
  background: none; border: 1px solid var(--border-base); color: var(--text-2);
  font-size: 12px; padding: 5px 14px; border-radius: 999px; cursor: pointer;
}
.mini-btn:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.mini-btn.danger:hover { color: #f87171; border-color: #f87171; }

.history-list { display: flex; flex-direction: column; gap: 10px; }
.history-item { padding: 12px 14px; cursor: pointer; position: relative; }
.history-item:hover { border-color: var(--brand-c2); }
.hi-row { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-3); }
.hi-status { padding: 1px 8px; border-radius: 999px; font-size: 11px; }
.hi-status.done { color: #6ee7b7; background: rgba(110,231,183,.1); }
.hi-status.failed, .hi-status.stopped { color: #f87171; background: rgba(248,113,113,.1); }
.hi-count { margin-left: auto; }
.hi-summary { margin-top: 6px; font-size: 13px; color: var(--text-1); }
.history-item .mini-btn.danger { position: absolute; right: 14px; top: 38px; }

.empty { text-align: center; color: var(--text-3); font-size: 13px; padding: 30px 0; }

.history-detail { display: flex; flex-direction: column; gap: 10px; }
.hi-title { font-size: 15px; font-weight: 600; color: var(--text-1); }
.hi-meta { font-size: 12px; color: var(--text-3); }
.msg-list { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.msg {
  border: 1px solid var(--border-base); border-radius: 10px;
  background: rgba(15,23,42,.6); padding: 8px 12px; font-size: 13px; color: var(--text-1);
  white-space: pre-wrap; word-break: break-word;
}
.msg.user { border-color: var(--brand-c2); }
.msg.tool { font-size: 12px; color: #a5b4fc; font-family: ui-monospace, Consolas, monospace; }
.msg-role { display: block; font-size: 11px; color: var(--text-3); margin-bottom: 4px; }
</style>
