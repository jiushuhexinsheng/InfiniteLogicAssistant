<template>
  <div ref="scrollEl" class="console-messages">
    <div v-if="!messages.length" class="console-empty">
      还没有对话 —— 点右下角悬浮球，或输入文字开始。
    </div>
    <div v-else class="console-msgs">
      <MessageItem
        v-for="m in messages"
        :key="m.id"
        :message="m"
        @retry="emit('retry', $event)"
        @cancel="emit('cancel', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import MessageItem from '../assistant/MessageItem.vue'
import type { ChatMessage } from '../../composables/useAssistant'

const props = defineProps<{ messages: ChatMessage[] }>()
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

const scrollEl = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  })
}

// 新消息或最后一条文本增长（流式回复）时滚到底
watch(
  () => [props.messages.length, props.messages[props.messages.length - 1]?.text?.length],
  scrollToBottom
)
onMounted(scrollToBottom)
</script>

<style scoped>
.console-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.console-msgs {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 2px 8px;
  max-width: 860px;
  width: 100%;
  margin: 0 auto;
}
.console-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  font-size: 13px;
}
</style>
