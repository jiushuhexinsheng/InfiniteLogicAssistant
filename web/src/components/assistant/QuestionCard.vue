<template>
  <!-- 提问卡片：按 kind 渲染成输入框 / 按钮 / 按钮加输入框（确认类即选项为确认与取消的 choice）。
       Question card: rendered per kind as an input, buttons, or buttons plus an input
       (a confirmation is just a choice whose options are confirm and cancel). -->
  <div v-if="q" class="confirm-card">
    <div class="confirm-title">❓ {{ title }}</div>
    <!-- 问题内容。Question content. -->
    <p class="confirm-q">{{ q.text }}</p>

    <!-- 选项按钮（choice / composite）。Option buttons (choice / composite). -->
    <div v-if="hasOptions" class="confirm-row">
      <button
        v-for="opt in q.options"
        :key="opt.value"
        class="confirm-btn"
        :class="{ primary: opt.value === 'yes' }"
        @click="choose(opt.value)"
      >{{ opt.label }}</button>
    </div>

    <!-- 文本输入（text / composite）。choice 下不渲染：自由文本会被后端判为未选择而拒绝，
         给了输入框只会让用户白输。Not rendered for choice, where free text is rejected by
         the backend as "no selection", so an input box would just waste the user's effort. -->
    <div v-if="allowText" class="confirm-row">
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

/** 待回答的提问（含作答方式与选项）。Pending question (with how to answer and its options). */
const q = asst.pendingQuestion

/** 卡片标题：按作答方式区分，让操作者一眼看出是确认还是追问。
 *  Card title: distinguished by how to answer, so the operator can tell a confirmation
 *  from a follow-up at a glance. */
const title = computed(() => (q.value?.kind === 'text' ? '需要你回答' : '需要你确认'))

/** 是否渲染选项按钮。Whether to render option buttons. */
const hasOptions = computed(() => !!q.value?.options.length)

/** 是否渲染文本输入（choice 下不渲染：自由文本会被后端判为未选择而拒绝）。
 *  Whether to render the text input (not for choice: free text is rejected by the backend
 *  as "no selection"). */
const allowText = computed(() => q.value?.kind !== 'choice')

/** 用户回答输入内容。User answer input content. */
const text = ref('')

/**
 * 提交自由文本回答：校验非空后发送并清空输入。
 * Submit a free-text answer: validate, send, then clear the input.
 */
function submit() {
  const v = text.value.trim()
  if (!v) return
  asst.sendAnswer(v)
  text.value = ''
}

/**
 * 提交选项回答：只回传选项的 value，不带文本。
 * Submit an option answer: returns only the option's value, with no text.
 *
 * @param value 选项的机器可读值。The option's machine-readable value.
 */
function choose(value: string) {
  asst.sendAnswer('', value)
}
</script>

<style scoped>
/* 确认卡片容器。Confirm card container. */
.confirm-card { border: 1px solid #f59e0b; border-radius: 10px; background: rgba(245, 158, 11, .06); padding: 10px 12px; margin: 0 10px 8px; }
/* 标题。Title. */
.confirm-title { font-size: 12px; font-weight: 600; color: var(--warn); margin-bottom: 4px; }
/* 问题文本。Question text. */
.confirm-q { font-size: 13px; margin: 0 0 8px; color: var(--text-1); }
/* 按钮行 / 输入行。Button row / input row. */
.confirm-row { display: flex; gap: 8px; }
.confirm-row + .confirm-row { margin-top: 8px; }
.confirm-row input { flex: 1; background: var(--surface-input); border: 1px solid var(--border-base); border-radius: 8px; color: var(--text-1); padding: 6px 10px; font-size: 13px; }
/* 普通按钮（回答 / 选项）。Plain button (answer / option). */
.confirm-btn { background: none; border: 1px solid #f59e0b; color: var(--warn); font-size: 12px; padding: 5px 14px; border-radius: 999px; cursor: pointer; }
/* 主按钮（确认）：高风险操作需与「取消」视觉上可区分。Primary button (confirm): must be visually distinct from "cancel" for a high-risk action. */
.confirm-btn.primary { background: rgba(245, 158, 11, .16); font-weight: 600; }
</style>
