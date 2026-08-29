<template>
  <div class="chat-input">
    <QuestionCard v-if="asst.pendingQuestion.value" />
    <div class="chat-input-row">
      <textarea
        ref="ta"
        v-model="text"
        rows="1"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        :disabled="disabled"
        @keydown.enter.exact.prevent="onEnter"
        @input="autosize"
      ></textarea>
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

const asst = useAssistant()
const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ send: [text: string] }>()

const text = ref('')
const ta = ref<HTMLTextAreaElement>()

function autosize() {
  const el = ta.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 4 * 20) + 'px'
}

function onEnter() { submit() }

function submit() {
  const v = text.value.trim()
  if (!v || props.disabled) return
  emit('send', v)
  text.value = ''
  nextTick(autosize)
}
</script>

<style scoped>
.chat-input {
  display: flex; flex-direction: column; gap: 8px;
  padding: 8px 12px;
  background: var(--surface-control);
  border: 1px solid var(--border-soft); border-radius: 16px;
  backdrop-filter: blur(12px) saturate(140%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  box-shadow: var(--shadow-2);
}
.chat-input-row { display: flex; align-items: flex-end; gap: 8px; }
.chat-input textarea {
  flex: 1; resize: none; max-height: 80px; min-height: 32px; line-height: 20px;
  background: transparent; border: none; color: var(--text-1);
  padding: 6px 4px; font-size: var(--fs-sm); outline: none; font-family: inherit;
}
.chat-input textarea:disabled { opacity: .5; }
.chat-input textarea::placeholder { color: var(--text-3); }
.ci-send {
  width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
  background: var(--brand-grad); border: none; color: var(--text-on-brand);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  box-shadow: var(--glow-brand);
}
.ci-send:disabled { opacity: .4; cursor: not-allowed; }
</style>
