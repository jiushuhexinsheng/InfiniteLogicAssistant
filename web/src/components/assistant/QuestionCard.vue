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

<style scoped>
.confirm-card { border: 1px solid #f59e0b; border-radius: 10px; background: rgba(245, 158, 11, .06); padding: 10px 12px; margin: 0 10px 8px; }
.confirm-title { font-size: 12px; font-weight: 600; color: var(--warn); margin-bottom: 4px; }
.confirm-q { font-size: 13px; margin: 0 0 8px; color: var(--text-1); }
.confirm-row { display: flex; gap: 8px; }
.confirm-row input { flex: 1; background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 8px; color: var(--text-1); padding: 6px 10px; font-size: 13px; }
.confirm-btn { background: none; border: 1px solid #f59e0b; color: var(--warn); font-size: 12px; padding: 5px 14px; border-radius: 999px; cursor: pointer; }
</style>
