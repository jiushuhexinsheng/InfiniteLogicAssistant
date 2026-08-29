<template>
  <div ref="scrollEl" class="console-messages">
    <div class="welcome">
      <span class="w-avatar"><UiIcon name="brain" :size="13" /></span>
      <span class="w-name">小逻</span>
      <span class="mono w-state">在线 · 说「{{ wakeKeyword }}」唤醒</span>
    </div>
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
import { UiIcon } from '../ui'
import type { ChatMessage } from '../../composables/useAssistant'

const props = withDefaults(defineProps<{ messages: ChatMessage[]; wakeKeyword?: string }>(), { wakeKeyword: '小逻' })
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

const scrollEl = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  })
}

watch(
  () => [props.messages.length, props.messages[props.messages.length - 1]?.text?.length],
  scrollToBottom
)
onMounted(scrollToBottom)
</script>

<style scoped>
.console-messages {
  flex: 1; min-height: 0; overflow-y: auto;
  display: flex; flex-direction: column;
}
.welcome {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 4px 12px;
}
.w-avatar {
  width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0;
  background: var(--brand-grad); color: var(--text-on-brand);
  display: grid; place-items: center;
}
.w-name { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); }
.w-state { font-size: var(--fs-2xs); color: var(--text-3); }
.console-msgs {
  display: flex; flex-direction: column; gap: 14px;
  padding: 4px 2px 8px; max-width: 860px; width: 100%; margin: 0 auto;
}
.console-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: var(--text-3); font-size: var(--fs-sm);
}
</style>
