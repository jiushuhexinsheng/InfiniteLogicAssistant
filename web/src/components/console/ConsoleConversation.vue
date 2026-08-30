<template>
  <div class="console-conv">
    <!-- 右上角浮动「新建会话」：顶部固定，消息滚动时不滚走 -->
    <div class="conv-top">
      <UiButton variant="secondary" size="sm" @click="newSession">＋ 新建会话</UiButton>
    </div>
    <ConsoleMessageList :messages="asst.messages.value" :wake-keyword="asst.wakeKeyword.value" @retry="asst.retryTool($event)" @cancel="asst.cancelTool($event)" />
    <div class="console-input">
      <ChatInput :disabled="false" @send="onSend" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { api } from '../../api'
import { useAssistant } from '../../composables/useAssistant'
import { createNewSession } from '../../composables/assistant/store'
import ConsoleMessageList from './ConsoleMessageList.vue'
import ChatInput from '../assistant/ChatInput.vue'
import { UiButton } from '../ui'

const asst = useAssistant()

function onSend(text: string) {
  asst.sendText(text)
}

/** 新建会话：清空当前对话，开启新的独立对话线 */
async function newSession() {
  try {
    const r = await api.createSession()
    createNewSession(r.session.id)
  } catch { /* ignore */ }
}
</script>

<style scoped>
.console-conv { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 10px; }
.conv-top {
  /* 顶部固定浮动：不随消息滚动 */
  display: flex; justify-content: flex-end;
  padding: 2px 4px 0;
  position: relative; z-index: 5;
}
.console-input { max-width: 880px; width: 100%; margin: 0 auto; padding-bottom: 6px; }
</style>
