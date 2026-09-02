<template>
  <!-- 聊天输入区域。Chat input area. -->
  <div class="chat-input">
    <!-- 待回答问题卡片（助手发起追问时显示）。Pending question card (shown when assistant asks a follow-up). -->
    <QuestionCard v-if="asst.pendingQuestion.value" />
    <div class="chat-input-row">
      <!-- 消息输入框：Enter 发送，Shift+Enter 换行。Message textarea: Enter to send, Shift+Enter for new line. -->
      <textarea
        ref="ta"
        v-model="text"
        rows="1"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        :disabled="disabled"
        @keydown.enter.exact.prevent="onEnter"
        @input="autosize"
      ></textarea>
      <!-- 发送按钮。Send button. -->
      <button class="ci-send" :disabled="disabled || !text.trim()" @click="submit">
        <UiIcon name="send" :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { UiIcon } from '../ui'
import QuestionCard from './QuestionCard.vue'
import { useAssistant } from '../../composables/useAssistant'

/** 获取助手实例。Get assistant instance. */
const asst = useAssistant()

/**
 * 组件属性定义。Component props definition.
 * @property disabled - 是否禁用输入。Whether the input is disabled.
 */
const props = defineProps<{ disabled?: boolean }>()

/**
 * 组件事件定义。Component events definition.
 * @event send - 发送消息事件，携带文本内容。Send message event with text payload.
 */
const emit = defineEmits<{ send: [text: string] }>()

/** 输入框文本内容。Textarea text content. */
const text = ref('')

/** textarea 元素引用。Textarea element reference. */
const ta = ref<HTMLTextAreaElement>()

/**
 * 自动调整 textarea 高度，最大 4 行。
 * Auto-resize textarea height, max 4 lines.
 */
function autosize() {
  const el = ta.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 4 * 20) + 'px'
}

/**
 * Enter 键触发提交。Enter key triggers submit.
 */
function onEnter() { submit() }

/**
 * 提交消息：校验非空后触发 send 事件并清空输入。
 * Submit message: emit send event after validation, then clear input.
 */
function submit() {
  const v = text.value.trim()
  if (!v || props.disabled) return
  emit('send', v)
  text.value = ''
  nextTick(autosize)
}
</script>

<style scoped>
/* 聊天输入容器。Chat input container. */
.chat-input {
  display: flex; flex-direction: column; gap: 8px;
  padding: 9px 12px;
  background: var(--surface-control);
  border: 1px solid var(--border-soft); border-radius: 16px;
  margin: 0 10px 10px;
  backdrop-filter: blur(12px) saturate(140%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  box-shadow: var(--shadow-2);
}
/* 输入行布局。Input row layout. */
.chat-input-row { display: flex; align-items: flex-end; gap: 8px; }
/* 输入框样式。Textarea styles. */
.chat-input textarea {
  flex: 1; resize: none; max-height: 80px; min-height: 32px; line-height: 20px;
  background: transparent; border: none; color: var(--text-1);
  padding: 6px 4px; font-size: var(--fs-sm); outline: none; font-family: inherit;
}
.chat-input textarea:disabled { opacity: .5; }
.chat-input textarea::placeholder { color: var(--text-3); }
/* 发送按钮。Send button. */
.ci-send {
  width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
  background: var(--brand-grad); border: none; color: var(--text-on-brand);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  box-shadow: var(--glow-brand);
}
.ci-send:disabled { opacity: .4; cursor: not-allowed; }
</style>
