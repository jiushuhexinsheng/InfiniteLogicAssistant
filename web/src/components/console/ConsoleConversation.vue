<template>
  <div class="console-conv">
    <ConsoleMessageList
      :messages="asst.messages.value"
      @retry="asst.retryTool($event)"
      @cancel="asst.cancelTool($event)"
    />
    <div class="console-input">
      <ChatInput :disabled="false" @send="onSend" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAssistant } from '../../composables/useAssistant'
import ConsoleMessageList from './ConsoleMessageList.vue'
import ChatInput from '../assistant/ChatInput.vue'

const asst = useAssistant()

function onSend(text: string) {
  asst.sendText(text)
}
</script>

<style scoped>
.console-conv {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.console-input {
  max-width: 860px;
  width: 100%;
  margin: 0 auto;
  padding-bottom: 8px;
}
</style>
