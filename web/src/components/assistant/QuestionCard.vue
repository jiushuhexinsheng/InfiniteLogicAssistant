<template>
  <!-- 提问卡片：助手发起追问时显示。确认类走结构化按钮，澄清类走自由文本。
       Question card: shown when the assistant asks a follow-up. Confirmation questions
       use structured buttons; clarification questions use free text. -->
  <div v-if="q" class="confirm-card">
    <div class="confirm-title">❓ {{ isConfirm ? '需要你确认' : '需要你回答' }}</div>
    <!-- 问题内容。Question content. -->
    <p class="confirm-q">{{ q.text }}</p>
    <!-- 确认类：只提供结构化按钮。自由文本会被后端判为未选择而拒绝（fail closed），
         故这里不提供输入框，避免用户输入后才发现不生效。
         Confirmation: structured buttons only. Free text is rejected as "no selection"
         by the backend (fail closed), so no input box is offered here. -->
    <div v-if="isConfirm" class="confirm-row">
      <button class="confirm-btn" @click="choose('no')">取消</button>
      <button class="confirm-btn primary" @click="choose('yes')">确认</button>
    </div>
    <!-- 澄清类：自由文本回答。Clarification: free-text answer. -->
    <div v-else class="confirm-row">
      <input v-model="text" placeholder="输入回答后回车…" @keydown.enter="submit" />
      <button class="confirm-btn" @click="submit">回答</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAssistant } from '../../composables/useAssistant'

/** 获取助手实例。Get assistant instance. */
const asst = useAssistant()

/** 待回答的提问（含提问类型）。Pending question (with its kind). */
const q = asst.pendingQuestion

/** 是否为确认类提问（渲染按钮而非输入框）。Whether this is a confirmation question (buttons instead of an input). */
const isConfirm = computed(() => q.value?.kind === 'confirm')

/** 用户回答输入内容。User answer input content. */
const text = ref('')

/**
 * 提交自由文本回答（澄清类）：校验非空后发送并清空输入。
 * Submit a free-text answer (clarification): validate, send, then clear the input.
 */
function submit() {
  const v = text.value.trim()
  if (!v) return
  asst.sendAnswer(v)
  text.value = ''
}

/**
 * 提交结构化确认（确认类）：只回传 choice，不带文本。
 * Submit a structured confirmation: returns only the choice, with no text.
 *
 * @param choice 结构化选择。The structured choice.
 */
function choose(choice: 'yes' | 'no') {
  asst.sendAnswer('', choice)
}
</script>

<style scoped>
/* 确认卡片容器。Confirm card container. */
.confirm-card { border: 1px solid #f59e0b; border-radius: 10px; background: rgba(245, 158, 11, .06); padding: 10px 12px; margin: 0 10px 8px; }
/* 标题。Title. */
.confirm-title { font-size: 12px; font-weight: 600; color: var(--warn); margin-bottom: 4px; }
/* 问题文本。Question text. */
.confirm-q { font-size: 13px; margin: 0 0 8px; color: var(--text-1); }
/* 回答行 / 按钮行。Answer row / button row. */
.confirm-row { display: flex; gap: 8px; }
.confirm-row input { flex: 1; background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 8px; color: var(--text-1); padding: 6px 10px; font-size: 13px; }
/* 普通按钮（回答 / 取消）。Plain button (answer / cancel). */
.confirm-btn { background: none; border: 1px solid #f59e0b; color: var(--warn); font-size: 12px; padding: 5px 14px; border-radius: 999px; cursor: pointer; }
/* 主按钮（确认）：高风险操作需与「取消」视觉上可区分。Primary button (confirm): must be visually distinct from "cancel" for a high-risk action. */
.confirm-btn.primary { background: rgba(245, 158, 11, .16); font-weight: 600; }
</style>
