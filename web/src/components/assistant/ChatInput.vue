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
        <Icon name="send" :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import Icon from '../Icon.vue'
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
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px;
  border-top: 1px solid var(--border-base);
}
.chat-input-row { display: flex; align-items: flex-end; gap: 8px; }
.chat-input textarea {
  flex: 1;
  resize: none;
  max-height: 80px;
  min-height: 36px;
  line-height: 20px;
  background: #1e293b;
  border: 1px solid var(--border-base);
  border-radius: 10px;
  color: var(--text-1);
  padding: 8px 10px;
  font-size: 13px;
  outline: none;
  font-family: inherit;
}
.chat-input textarea:focus { border-color: var(--brand-c2); }
.chat-input textarea:disabled { opacity: .5; }
.ci-send {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--brand-grad);
  border: none;
  color: #0f172a;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ci-send:disabled { opacity: .4; cursor: not-allowed; }
</style>
