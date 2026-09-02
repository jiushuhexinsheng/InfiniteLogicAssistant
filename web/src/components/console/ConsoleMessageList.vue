<template>
  <div ref="scrollEl" class="console-messages">
    <!-- 欢迎横幅：显示助手名称、在线状态和唤醒词。Welcome banner: shows assistant name, online status and wake keyword. -->
    <div class="welcome">
      <span class="w-avatar"><UiIcon name="brain" :size="13" /></span>
      <span class="w-name">小逻</span>
      <span class="mono w-state">在线 · 说「{{ wakeKeyword }}」唤醒</span>
    </div>
    <div v-if="!messages.length" class="console-empty">
      还没有对话 —— 点右下角悬浮球，或输入文字开始。
    </div>
    <!-- 消息列表：遍历渲染每条聊天消息，支持重试和取消工具调用。Message list: renders each chat message with retry and cancel tool-call support. -->
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

/** 组件 props：消息列表和可选的唤醒关键词。Component props: message list and optional wake keyword. */
const props = withDefaults(defineProps<{ messages: ChatMessage[]; wakeKeyword?: string }>(), { wakeKeyword: '小逻' })
/** 组件事件：重试工具调用和取消工具调用。Component events: retry and cancel tool calls. */
const emit = defineEmits<{ retry: [id: string]; cancel: [id: string] }>()

/** 滚动容器 DOM 引用。Scroll container DOM reference. */
const scrollEl = ref<HTMLElement | null>(null)

/** 平滑滚动到底部（在 DOM 更新后执行）。Smooth scroll to bottom (executes after DOM update). */
function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  })
}

/** 监听消息数量和最后一条消息长度变化，自动滚到底部。Watch message count and last message length changes, auto-scroll to bottom. */
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
  padding: 4px 4px 14px;
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
  padding: 4px 2px 10px; max-width: 860px; width: 100%; margin: 0 auto;
}
.console-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: var(--text-3); font-size: var(--fs-sm);
}
</style>
