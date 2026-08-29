<template>
  <div class="console-task">
    <div class="task-input">
      <UiTextarea v-model="input" :rows="2" placeholder="输入指令，如：把桌面 readme.txt 复制到下载" @keydown.enter.exact.prevent="send" />
      <div class="task-actions">
        <UiButton variant="secondary" size="sm" :disabled="running" @click="send">发送</UiButton>
        <UiButton v-if="sessionId && running" variant="secondary" size="sm" hover="danger" @click="stop">停止</UiButton>
      </div>
    </div>

    <div v-if="log.length" class="task-log">
      <div v-for="(line, i) in log" :key="i" class="log-line" :class="line.kind">{{ line.text }}</div>
    </div>

    <div v-if="pendingQuestion" class="confirm-card">
      <div class="confirm-title">❓ 需要你回答</div>
      <p class="confirm-q">{{ pendingQuestion }}</p>
      <div class="confirm-row">
        <UiInput v-model="answer" placeholder="输入回答后回车…" @keydown.enter="sendAnswer" />
        <UiButton variant="secondary" size="sm" @click="sendAnswer">回答</UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api, streamUtter } from '../../api'
import { UiButton, UiInput, UiTextarea } from '../ui'

const input = ref('')
const answer = ref('')
const sessionId = ref('')
const pendingQuestion = ref('')
const running = ref(false)
const log = ref<{ kind: string; text: string }[]>([])

function push(kind: string, text: string) {
  log.value.push({ kind, text })
}

async function send() {
  const text = input.value.trim()
  if (!text || running.value) return
  running.value = true
  pendingQuestion.value = ''
  log.value = []
  push('user', text)
  sessionId.value = await streamUtter(text, {
    onTaskState: (s) => {
      if (s.state === 'understanding') push('state', '🧠 理解中…')
      if (s.state === 'done') {
        push('state', '✅ ' + s.status + ': ' + s.summary)
        if (s.steps?.length) {
          for (const st of s.steps) push('tool', '🔧 ' + st.tool + ' ' + st.status + ' → ' + st.result)
        }
      }
    },
    onContent: (t) => push('assistant', t),
    onQuestion: ({ question }) => { pendingQuestion.value = question },
    onError: (m) => push('error', '❌ ' + m),
    onDone: () => { running.value = false },
  })
}

async function sendAnswer() {
  const a = answer.value.trim()
  if (!a) return
  push('user', '（回答）' + a)
  try {
    await api.answer(sessionId.value, a)
    pendingQuestion.value = ''
    answer.value = ''
  } catch (e: any) {
    push('error', '❌ 回答投递失败: ' + (e?.message || ''))
  }
}

async function stop() {
  try {
    await api.stopTask(sessionId.value)
    push('state', '🛑 已发送停止指令')
  } catch (e: any) {
    push('error', '❌ 停止失败: ' + (e?.message || ''))
  }
}
</script>

<style scoped>
.console-task { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }
.task-input { display: flex; flex-direction: column; gap: 8px; }
.task-actions { display: flex; gap: 8px; }
.task-log { display: flex; flex-direction: column; gap: 6px; }
.log-line { font-size: 12px; padding: 6px 10px; border-radius: 8px; background: var(--surface-control); color: var(--text-2); word-break: break-word; }
.log-line.user { color: var(--text-1); border-left: 2px solid var(--brand-c2); }
.log-line.state { color: var(--info); }
.log-line.tool { color: var(--brand-c1); font-family: var(--font-mono); font-size: 11px; }
.log-line.assistant { color: var(--text-1); background: var(--surface-raised); }
.log-line.error { color: var(--err); }

/* 澄清/确认问题卡片（与悬浮助手 QuestionCard 一致） */
.confirm-card { border: 1px solid #f59e0b; border-radius: 10px; background: rgba(245, 158, 11, .06); padding: 10px 12px; }
.confirm-title { font-size: 12px; font-weight: 600; color: var(--warn); margin-bottom: 4px; }
.confirm-q { font-size: 13px; margin: 0 0 8px; color: var(--text-1); }
.confirm-row { display: flex; gap: 8px; align-items: center; }
</style>
