<template>
  <!-- 聊天输入区域。提问交互由 question 块承载（消息流内的 QuestionBlock），
       此处不再挂重复的 QuestionCard（收敛：系统-操作员对话模块唯一）。
       Chat input area. Question interaction is carried by the question block
       (QuestionBlock in the message stream); the duplicate QuestionCard is no
       longer mounted here (converged: one system-operator dialogue module). -->
  <div class="chat-input">
    <!-- 排队徽标（docs/designs/06 批3）：回合进行中发送的消息在此排队，点击清空。
         Queued badge (docs/designs/06 batch 3): messages sent while a turn runs wait
         here; click to clear. -->
    <button v-if="queueCount > 0" type="button" class="ci-queue" @click="clearQueued()">
      排队 {{ queueCount }} 条 · 点击清空
    </button>
    <div class="chat-input-row">
      <!-- 消息输入框：Enter 发送，Shift+Enter 换行；UiTextarea 自动增高至 4 行。
           Message textarea: Enter to send, Shift+Enter for newline; UiTextarea autosizes to 4 rows. -->
      <UiTextarea
        v-model="text"
        class="ci-ta"
        :rows="1"
        :autosize="true"
        :max-rows="4"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        :disabled="disabled"
        @keydown.enter.exact.prevent="onEnter"
      />
      <!-- 发送按钮。Send button. -->
      <UiIconButton
        title="发送"
        variant="brand"
        circle
        :disabled="disabled || !text.trim()"
        @click="submit"
      >
        <UiIcon name="send" :size="16" />
      </UiIconButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { UiIconButton, UiIcon, UiTextarea } from '../ui'
import { outboxCount as queueCount, clearQueued } from '../../composables/assistant/useChat'

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

/**
 * Enter 键触发提交。Enter key triggers submit.
 */
function onEnter() { submit() }

/**
 * 提交消息：校验非空后触发 send 事件并清空输入（UiTextarea watch 自动收敛高度）。
 * Submit message: emit send event after validation, then clear input (UiTextarea's watch converges the height).
 */
function submit() {
  const v = text.value.trim()
  if (!v || props.disabled) return
  emit('send', v)
  text.value = ''
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
/* 排队徽标（可点击清空）。Queued badge (click to clear). */
.ci-queue {
  align-self: flex-start;
  border: 1px dashed rgba(251, 191, 36, .45);
  background: rgba(251, 191, 36, .08);
  color: var(--text-2);
  font-size: var(--fs-2xs);
  border-radius: 999px;
  padding: 3px 10px;
  cursor: pointer;
}
.ci-queue:hover { color: var(--text-1); border-color: rgba(251, 191, 36, .8); }
/* 输入框：融入容器（透明底无边框），保留 UiTextarea 的自动增高。
   Input: blends into the container (transparent, borderless), keeps UiTextarea's autosize. */
.chat-input :deep(.ci-ta) {
  flex: 1; resize: none; background: transparent; border: none;
  box-shadow: none; /* 清掉 UiTextarea 的凹陷阴影（容器已是透明设计）。Drop UiTextarea's inset shadow (container is transparent by design). */
  min-height: 32px; max-height: 80px; line-height: 20px;
  padding: 6px 4px; color: var(--text-1); font-size: var(--fs-sm);
}
.chat-input :deep(.ci-ta:hover:not(:disabled)) { border-color: transparent; box-shadow: none; }
.chat-input :deep(.ci-ta:focus) { box-shadow: none; }
.chat-input :deep(.ci-ta:focus-visible) { outline: var(--focus-ring); outline-offset: -1px; }
</style>
