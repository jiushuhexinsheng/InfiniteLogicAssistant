<template>
  <div class="console-task">
    <div class="task-input">
      <textarea v-model="input" rows="2" placeholder="输入指令，如：把桌面 readme.txt 复制到下载" @keydown.enter.exact.prevent="send"></textarea>
      <div class="task-actions">
        <button class="mini-btn" :disabled="running" @click="send">发送</button>
        <button v-if="sessionId && running" class="mini-btn danger" @click="stop">停止</button>
      </div>
    </div>

    <!-- 执行流日志 -->
    <div v-if="log.length" class="task-log">
      <div v-for="(line, i) in log" :key="i" class="log-line" :class="line.kind">{{ line.text }}</div>
    </div>

    <!-- 待澄清/确认问题卡片 -->
    <div v-if="pendingQuestion" class="card confirm-card">
      <div class="card-title">❓ 需要你回答</div>
      <p class="confirm-q">{{ pendingQuestion }}</p>
      <div class="confirm-row">
        <input v-model="answer" placeholder="输入回答后回车…" @keydown.enter="sendAnswer" />
        <button class="mini-btn" @click="sendAnswer">回答</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api, streamUtter } from '../../api'

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
        push('state', `✅ ${s.status}: ${s.summary}`)
        if (s.steps?.length) {
          for (const st of s.steps) push('tool', `🔧 ${st.tool} ${st.status} → ${st.result}`)
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
.task-input textarea {
  width: 100%;
  resize: vertical;
  background: #0b1120;
  border: 1px solid var(--border-base);
  border-radius: 10px;
  color: var(--text-1);
  padding: 10px 12px;
  font-size: 13px;
  font-family: inherit;
}
.task-actions { display: flex; gap: 8px; margin-top: 8px; }
.mini-btn {
  background: none;
  border: 1px solid var(--border-base);
  color: var(--text-2);
  font-size: 12px;
  padding: 5px 14px;
  border-radius: 999px;
  cursor: pointer;
}
.mini-btn:hover:not(:disabled) { color: var(--brand-c2); border-color: var(--brand-c2); }
.mini-btn:disabled { opacity: .5; cursor: default; }
.mini-btn.danger:hover { color: #f87171; border-color: #f87171; }

.task-log { display: flex; flex-direction: column; gap: 6px; }
.log-line {
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--border-base);
  background: rgba(15, 23, 42, .6);
  white-space: pre-wrap;
  word-break: break-word;
}
.log-line.user { border-color: var(--brand-c2); color: var(--text-1); }
.log-line.assistant { color: var(--text-1); }
.log-line.state { color: var(--brand-c2); }
.log-line.tool { color: #a5b4fc; font-family: ui-monospace, Consolas, monospace; font-size: 11px; }
.log-line.error { color: #f87171; }

.confirm-card { border: 1px solid #f59e0b; }
.confirm-q { font-size: 13px; margin: 0 0 10px; }
.confirm-row { display: flex; gap: 8px; }
.confirm-row input {
  flex: 1;
  background: #0b1120;
  border: 1px solid var(--border-base);
  border-radius: 8px;
  color: var(--text-1);
  padding: 6px 10px;
  font-size: 13px;
}
</style>
