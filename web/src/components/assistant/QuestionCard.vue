<template>
  <!-- 确认卡片：助手发起追问时显示，用户输入回答后提交。Confirm card: shown when assistant asks a follow-up question, user submits answer. -->
  <div class="confirm-card">
    <div class="confirm-title">❓ 需要你回答</div>
    <!-- 问题内容。Question content. -->
    <p class="confirm-q">{{ question }}</p>
    <!-- 回答输入行。Answer input row. -->
    <div class="confirm-row">
      <input v-model="answer" placeholder="输入回答后回车…" @keydown.enter="submit" />
      <button class="confirm-btn" @click="submit">回答</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAssistant } from '../../composables/useAssistant'

/** 获取助手实例。Get assistant instance. */
const asst = useAssistant()

/** 用户回答输入内容。User answer input content. */
const answer = ref('')

/** 待回答的问题文本（来自助手 pendingQuestion）。Pending question text (from assistant pendingQuestion). */
const question = asst.pendingQuestion

/**
 * 提交回答：校验非空后发送给助手并清空输入。
 * Submit answer: send to assistant after validation, then clear input.
 */
function submit() {
  const v = answer.value.trim()
  if (!v) return
  asst.sendAnswer(v)
  answer.value = ''
}
</script>

<style scoped>
/* 确认卡片容器。Confirm card container. */
.confirm-card { border: 1px solid #f59e0b; border-radius: 10px; background: rgba(245, 158, 11, .06); padding: 10px 12px; margin: 0 10px 8px; }
/* 标题。Title. */
.confirm-title { font-size: 12px; font-weight: 600; color: var(--warn); margin-bottom: 4px; }
/* 问题文本。Question text. */
.confirm-q { font-size: 13px; margin: 0 0 8px; color: var(--text-1); }
/* 回答输入行。Answer input row. */
.confirm-row { display: flex; gap: 8px; }
.confirm-row input { flex: 1; background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 8px; color: var(--text-1); padding: 6px 10px; font-size: 13px; }
/* 回答按钮。Submit button. */
.confirm-btn { background: none; border: 1px solid #f59e0b; color: var(--warn); font-size: 12px; padding: 5px 14px; border-radius: 999px; cursor: pointer; }
</style>
