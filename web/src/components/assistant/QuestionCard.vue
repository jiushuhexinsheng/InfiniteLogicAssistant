<template>
  <div class="confirm-card">
    <div class="confirm-title">❓ 需要你回答</div>
    <p class="confirm-q">{{ question }}</p>
    <div class="confirm-row">
      <input v-model="answer" placeholder="输入回答后回车…" @keydown.enter="submit" />
      <button class="confirm-btn" @click="submit">回答</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAssistant } from '../../composables/useAssistant'

const asst = useAssistant()
const answer = ref('')

const question = asst.pendingQuestion

function submit() {
  const v = answer.value.trim()
  if (!v) return
  asst.sendAnswer(v)
  answer.value = ''
}
</script>
