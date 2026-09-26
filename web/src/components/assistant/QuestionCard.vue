<template>
  <!-- 薄壳：把 pendingQuestion 包装成 question 块交给 QuestionBlock 渲染。
       系统-操作员对话模块唯一实现是 QuestionBlock；本组件只服务摘要皮肤宿主
       （悬浮面板：MiniHistory 不渲染交互块，需要独立的作答面）。
       Thin shell: wraps pendingQuestion into a question block for QuestionBlock.
       QuestionBlock is the single implementation of the system-operator dialogue
       module; this shell only serves summary-skin hosts (the floating panel,
       whose MiniHistory renders no interactive blocks and needs its own answer
       surface). -->
  <QuestionBlock v-if="block" :block="block" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import QuestionBlock from '../blocks/QuestionBlock.vue'
import { pendingQuestion } from '../../composables/assistant/store'
import { makeBlock } from '../../blocks/normalize'
import type { Block } from '../../blocks/types'

/** pendingQuestion → 临时 question 块（作答走 sendAnswer，与流内块同一通道）。 */
const block = computed<Block | null>(() => {
  const q = pendingQuestion.value
  if (!q) return null
  return makeBlock('question', {
    qid: q.qid,
    question: q.text,
    kind: q.kind,
    options: q.options,
    status: 'pending',
  })
})
</script>
