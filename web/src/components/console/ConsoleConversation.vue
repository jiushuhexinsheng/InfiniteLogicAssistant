<template>
  <div class="console-conv">
    <!-- 右上角浮动「新建会话」：顶部固定，消息滚动时不滚走。Floating "New Session" button at top-right: fixed at top, won't scroll away with messages. -->
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
import { notify } from '../../composables/useToast'
import { formatError } from '../../errors'
import ConsoleMessageList from './ConsoleMessageList.vue'
import ChatInput from '../assistant/ChatInput.vue'
import { UiButton } from '../ui'

/** 当前助手实例，提供消息列表、发送文本等能力。Current assistant instance providing messages, sendText, etc. */
const asst = useAssistant()

/** 处理用户发送消息：将文本转发给助手。Handle user send: forward text to the assistant. */
function onSend(text: string) {
  asst.sendText(text)
}

/** 新建会话：清空当前对话，开启新的独立对话线。Create a new session: clear current conversation and start a fresh independent thread. */
async function newSession() {
  try {
    const r = await api.createSession()
    createNewSession(r.session.id)
    notify.ok('已新建会话')
  } catch (e) {
    notify.err('新建会话失败：' + formatError(e))
  }
}
</script>

<style scoped>
.console-conv { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; }
.conv-top {
  /* 顶部固定浮动：不随消息滚动。Fixed floating at top: does not scroll with messages. */
  display: flex; justify-content: flex-end;
  padding: 2px 4px 0;
  position: relative; z-index: 5;
}
.console-input { max-width: 880px; width: 100%; margin: 0 auto; padding-bottom: 8px; }
</style>
