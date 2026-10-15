<template>
  <div ref="scrollEl" class="console-messages">
    <!-- 欢迎横幅（衍衡/在线状态行）已移除（2026-10-11 用户要求：对话页去掉身份头，
         状态信息由悬浮球状态胶囊与侧栏承担）。
         The welcome banner (衍衡 / online-status row) is removed (2026-10-11 user
         request: drop the identity header from the conversation page — status lives on
         the float-ball pill and the sidebar). -->
    <!-- 对话区空态：长满会话区并居中（UiEmpty 的默认行为）。图标 = 侧栏「对话」页签的 messages-square。
         Conversation empty state: fills the pane and centres itself (UiEmpty's default now). The icon
         is the 对话 sidebar tab's `messages-square`. -->
    <UiEmpty v-if="!messages.length" icon="messages-square"
      text="还没有对话" hint="点右下角悬浮球，或输入文字开始" />
    <!-- 消息列表：遍历渲染每条聊天消息，支持重试/取消工具与消息级 分叉/编辑/重生成（docs/designs/07）。
         Message list: renders each chat message with tool retry/cancel plus message-level
         fork/edit/regenerate (docs/designs/07). -->
    <div v-else class="console-msgs">
      <MessageItem
        v-for="(m, i) in messages"
        :key="m.id"
        :message="m"
        :index="i"
        :can-act="canAct"
        @retry="emit('retry', $event)"
        @cancel="emit('cancel', $event)"
        @fork="emit('fork', $event)"
        @edit="(idx, text) => emit('edit', idx, text)"
        @regen="emit('regen', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import MessageItem from '../assistant/MessageItem.vue'
import { UiEmpty } from '../ui'
import type { ChatMessage } from '../../composables/useAssistant'

/** 组件 props：消息列表、消息级动作开关（回合空闲且有会话）。
 *  Component props: message list, message-level action switch. */
const props = withDefaults(
  defineProps<{ messages: ChatMessage[]; canAct?: boolean }>(),
  { canAct: false },
)
/** 组件事件：工具重试/取消 + 消息分叉/编辑/重生成。Component events. */
const emit = defineEmits<{
  retry: [id: string]
  cancel: [id: string]
  fork: [index: number]
  edit: [index: number, text: string]
  regen: [index: number]
}>()

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
.console-msgs {
  display: flex; flex-direction: column; gap: var(--sp-q14);
  padding: var(--sp-1) var(--sp-q2) var(--sp-q10); max-width: 860px; width: 100%; margin: 0 auto;
}
</style>
