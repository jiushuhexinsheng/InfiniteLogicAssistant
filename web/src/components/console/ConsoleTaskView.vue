<template>
  <div class="console-task">
    <!-- 任务输入区：指令输入框、发送和停止按钮。Task input area: command input, send and stop buttons. -->
    <div class="task-input">
      <UiTextarea v-model="input" :rows="2" placeholder="输入指令，如：把桌面 readme.txt 复制到下载" @keydown.enter.exact.prevent="send" />
      <div class="task-actions">
        <UiButton variant="secondary" size="sm" :disabled="isBusy" @click="send">发送</UiButton>
        <UiButton v-if="currentSessionId && isBusy" variant="secondary" size="sm" hover="danger" @click="stop">停止</UiButton>
      </div>
    </div>

    <!-- 任务执行日志：共享消息流经 BlockHost 以 task 皮肤渲染（紧凑平铺日志）。
         独立流消费/重复问题卡已收敛 —— 提问即 question 块（QuestionBlock 交互），
         与对话 tab 同一份数据、同一套块协议。
         Task execution log: the shared message stream renders via BlockHost with the
         task skin (compact flat log). The private stream and duplicate question card
         are converged away — a question is a question block (QuestionBlock interactive),
         same data and block protocol as the conversation tab. -->
    <div v-if="messages.length" class="task-log">
      <div v-for="m in messages" :key="m.id" class="log-entry" :class="m.role">
        <BlockHost :blocks="m.blocks || []" skin="task" @retry="retryTool" @cancel="cancelTool" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../../api'
import { formatError } from '../../errors'
import { UiButton, UiTextarea } from '../ui'
import BlockHost from '../blocks/BlockHost.vue'
import { messages, currentSessionId, state, addMessage } from '../../composables/assistant/store'
import { runTurn, retryTool, cancelTool } from '../../composables/assistant/useChat'

/** 用户指令输入。User command input. */
const input = ref('')

/** 任务是否在跑（复用助手状态机，不再私有 running 标志）。Whether a task is running (shared state machine, no private flag). */
const isBusy = computed(() => ['thinking', 'tool_calling', 'responding', 'transcribing'].includes(state.value))

/** 发送任务指令：走共享 useChat 管线（与语音/对话 tab 同一条编排 SSE）。
 *  Send task command: shared useChat pipeline (same orchestration SSE as voice/conversation). */
async function send() {
  const text = input.value.trim()
  if (!text || isBusy.value) return
  input.value = ''
  addMessage('user', text)
  await runTurn()
}

/** 停止当前正在运行的任务。Stop the currently running task. */
async function stop() {
  try {
    await api.stopTask(currentSessionId.value)
  } catch (e) {
    addMessage('system', '停止失败：' + formatError(e))
  }
}
</script>

<style scoped>
.console-task { max-width: 720px; width: 100%; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; flex: 1; min-height: 0; overflow-y: auto;}
.task-input { display: flex; flex-direction: column; gap: 8px; }
.task-actions { display: flex; gap: 8px; }
.task-log { display: flex; flex-direction: column; gap: 6px; }
.log-entry { padding: 6px 10px; border-radius: 8px; background: var(--surface-control); word-break: break-word; }
.log-entry.user { border-left: 2px solid var(--brand-c2); }
.log-entry.system { border-left: 2px solid var(--err); }
</style>
