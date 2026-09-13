<template>
  <div class="console-task">
    <!-- 任务输入区：指令输入框、发送和停止按钮。Task input area: command input, send and stop buttons. -->
    <div class="task-input">
      <UiTextarea v-model="input" :rows="2" placeholder="输入指令，如：把桌面 readme.txt 复制到下载" @keydown.enter.exact.prevent="send" />
      <div class="task-actions">
        <UiButton variant="secondary" size="sm" :disabled="running" @click="send">发送</UiButton>
        <UiButton v-if="sessionId && running" variant="secondary" size="sm" hover="danger" @click="stop">停止</UiButton>
      </div>
    </div>

    <!-- 任务执行日志：展示用户输入、状态变化、工具调用和助手回复。Task execution log: shows user input, state changes, tool calls and assistant replies. -->
    <div v-if="log.length" class="task-log">
      <div v-for="(line, i) in log" :key="i" class="log-line" :class="line.kind">{{ line.text }}</div>
    </div>

    <!-- 澄清/确认问题卡片：任务需要用户回答时显示。确认类走结构化按钮，澄清类走自由文本。
         Clarification/confirmation card: confirmation questions use structured buttons,
         clarification questions use free text. -->
    <div v-if="pendingQuestion" class="confirm-card">
      <div class="confirm-title">❓ {{ isConfirm ? '需要你确认' : '需要你回答' }}</div>
      <p class="confirm-q">{{ pendingQuestion.text }}</p>
      <!-- 确认类：只提供按钮。后端对确认类只接受结构化 choice，自由文本仅精确
           等于「确认」等字面量才生效 —— 给输入框只会让用户白输（并被取消任务）。
           Confirmation: buttons only. The backend accepts only a structured choice for
           confirmation; free text works only on an exact literal match, so offering an
           input box would just waste the user's effort (and cancel the task). -->
      <div v-if="isConfirm" class="confirm-row">
        <UiButton variant="secondary" size="sm" @click="choose('no')">取消</UiButton>
        <UiButton variant="primary" size="sm" @click="choose('yes')">确认</UiButton>
      </div>
      <!-- 澄清类：自由文本回答。Clarification: free-text answer. -->
      <div v-else class="confirm-row">
        <UiInput v-model="answer" placeholder="输入回答后回车…" @keydown.enter="sendAnswer" />
        <UiButton variant="secondary" size="sm" @click="sendAnswer">回答</UiButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, streamUtter } from '../../api'
import { formatError } from '../../errors'
import { UiButton, UiInput, UiTextarea } from '../ui'

/** 用户指令输入。User command input. */
const input = ref('')
/** 用户对澄清问题的回答。User's answer to clarification question. */
const answer = ref('')
/** 当前流式会话 ID。Current streaming session ID. */
const sessionId = ref('')
/** 待回答的提问（含提问类型，决定渲染按钮还是输入框）。Pending question (with its kind, which decides buttons vs. an input). */
const pendingQuestion = ref<{ text: string; kind: 'clarify' | 'confirm' } | null>(null)
/** 是否为确认类提问。Whether this is a confirmation question. */
const isConfirm = computed(() => pendingQuestion.value?.kind === 'confirm')
/** 任务是否正在运行。Whether a task is running. */
const running = ref(false)
/** 任务执行日志（kind: user/state/tool/assistant/error）。Task execution log (kind: user/state/tool/assistant/error). */
const log = ref<{ kind: string; text: string }[]>([])

/** 向日志追加一条记录。Append a record to the log. */
function push(kind: string, text: string) {
  log.value.push({ kind, text })
}

/** 发送任务指令：通过 SSE 流式执行任务并实时更新日志。Send task command: execute task via SSE streaming and update log in real-time. */
async function send() {
  const text = input.value.trim()
  if (!text || running.value) return
  running.value = true
  pendingQuestion.value = null
  log.value = []
  push('user', text)
  const sid = await streamUtter(text, {
    onTaskState: (s) => {
      // 流进行中就要拿到 session_id：作答与停止都发生在流结束之前，
      // 只靠 streamUtter 的返回值会在作答时拿到空串（404）。
      // Capture session_id while the stream is running: answering and stopping both
      // happen before it ends, so relying solely on streamUtter's return value would
      // yield an empty id at answer time (404).
      if (s.session_id) sessionId.value = s.session_id
      if (s.state === 'understanding') push('state', '🧠 理解中…')
      if (s.state === 'done') {
        push('state', '✅ ' + s.status + ': ' + s.summary)
        if (s.steps?.length) {
          for (const st of s.steps) push('tool', '🔧 ' + st.tool + ' ' + st.status + ' → ' + st.result)
        }
      }
    },
    onContent: (t) => push('assistant', t),
    onQuestion: ({ question, kind, session_id }) => {
      if (session_id) sessionId.value = session_id
      // kind 决定渲染按钮还是输入框；缺省按澄清处理（向后兼容无该字段的后端）。
      // kind decides buttons vs. input; default to clarify (backward compatible with
      // a backend that omits the field).
      pendingQuestion.value = { text: question, kind: kind === 'confirm' ? 'confirm' : 'clarify' }
    },
    onError: (m) => push('error', '❌ ' + m),
    onDone: () => { running.value = false },
  })
  // 事件未携带 session_id 时兜底用返回值；反之保留事件里的（不覆盖）。
  // Fall back to the return value when no event carried an id; otherwise keep the
  // event-derived one (do not overwrite).
  if (sid) sessionId.value = sid
}

/** 发送用户对澄清问题的自由文本回答。Send the user's free-text answer to a clarification question. */
async function sendAnswer() {
  const a = answer.value.trim()
  if (!a) return
  push('user', '（回答）' + a)
  try {
    await api.answer(sessionId.value, a)
    pendingQuestion.value = null
    answer.value = ''
  } catch (e) {
    push('error', '❌ 回答投递失败：' + formatError(e))
  }
}

/**
 * 发送结构化确认（确认类提问）：只回传 choice，不带文本。
 * Send a structured confirmation (confirmation questions): returns only the choice, with no text.
 *
 * @param choice 结构化选择。The structured choice.
 */
async function choose(choice: 'yes' | 'no') {
  if (!pendingQuestion.value) return
  push('user', choice === 'yes' ? '（确认执行）' : '（取消执行）')
  try {
    await api.answer(sessionId.value, '', choice)
    pendingQuestion.value = null
  } catch (e) {
    push('error', '❌ 回答投递失败：' + formatError(e))
  }
}

/** 停止当前正在运行的任务。Stop the currently running task. */
async function stop() {
  try {
    await api.stopTask(sessionId.value)
    push('state', '🛑 已发送停止指令')
  } catch (e) {
    push('error', '❌ 停止失败：' + formatError(e))
  }
}
</script>

<style scoped>
.console-task { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; flex: 1; min-height: 0; overflow-y: auto;}
.task-input { display: flex; flex-direction: column; gap: 8px; }
.task-actions { display: flex; gap: 8px; }
.task-log { display: flex; flex-direction: column; gap: 6px; }
.log-line { font-size: 12px; padding: 6px 10px; border-radius: 8px; background: var(--surface-control); color: var(--text-2); word-break: break-word; }
.log-line.user { color: var(--text-1); border-left: 2px solid var(--brand-c2); }
.log-line.state { color: var(--info); }
.log-line.tool { color: var(--brand-c1); font-family: var(--font-mono); font-size: 11px; }
.log-line.assistant { color: var(--text-1); background: var(--surface-raised); }
.log-line.error { color: var(--err); }

/* 澄清/确认问题卡片（与悬浮助手 QuestionCard 一致）。Clarification/confirm card (consistent with floating assistant QuestionCard). */
.confirm-card { border: 1px solid #f59e0b; border-radius: 10px; background: rgba(245, 158, 11, .06); padding: 10px 12px; }
.confirm-title { font-size: 12px; font-weight: 600; color: var(--warn); margin-bottom: 4px; }
.confirm-q { font-size: 13px; margin: 0 0 8px; color: var(--text-1); }
.confirm-row { display: flex; gap: 8px; align-items: center; }
</style>
