<template>
  <!-- 系统-操作员对话模块（提问侧）：自由文本为主，选项为预留扩展点。
       已答后折叠为只读态（与 answer 块配对展示）。
       System-operator dialogue (question side): free text first, options are a
       reserved extension point. Collapses to read-only once answered. -->
  <div class="blk-question" :class="[skin, block.payload.status || 'pending']">
    <template v-if="isPending">
      <div class="q-title">❓ {{ kind === 'text' ? '需要你回答' : '需要你确认' }}</div>
      <p class="q-text">{{ block.payload.question }}</p>
      <!-- 选项按钮（choice / composite；语音兼容：label 即语音精确匹配接口，勿随意改）。
           Option buttons (voice-compatible: the label is the exact-match speech interface). -->
      <div v-if="hasOptions" class="q-row">
        <UiButton
          v-for="opt in block.payload.options"
          :key="opt.value"
          shape="square"
          :variant="opt.value === 'yes' ? 'primary' : 'secondary'"
          @click="choose(opt.value)"
        >{{ opt.label }}</UiButton>
      </div>
      <!-- choice 下不渲染输入框：自由文本会被后端判为未选择而拒绝。
           No input for choice: free text is rejected as "no selection" by the backend. -->
      <div v-if="allowText" class="q-row">
        <UiInput
          v-model="text"
          class="q-input"
          placeholder="输入回答后回车…"
          @keydown.enter="submit"
        />
        <UiButton shape="square" variant="secondary" @click="submit">回答</UiButton>
      </div>
    </template>
    <div v-else class="q-answered">
      <span class="q-label">❓ {{ block.payload.question }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { UiButton, UiInput } from '../ui'
import { sendAnswer } from '../../composables/assistant/useChat'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 提问块。Question block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 是否仍待答。Whether still pending. */
const isPending = computed(() => props.block.payload.status !== 'answered')

/** 作答方式（自由文本为主；缺省 text）。How to answer (free text first). */
const kind = computed(() => props.block.payload.kind || 'text')

/** 是否渲染选项按钮。Whether to render option buttons. */
const hasOptions = computed(() => !!props.block.payload.options?.length)

/** 是否渲染文本输入（choice 下不渲染）。Whether to render the text input. */
const allowText = computed(() => kind.value !== 'choice')

/** 用户回答输入内容。User answer input. */
const text = ref('')

/** 提交自由文本回答。Submit a free-text answer. */
function submit() {
  const v = text.value.trim()
  if (!v) return
  sendAnswer(v)
  text.value = ''
}

/** 提交选项回答（只回传 value）。Submit an option answer (value only). */
function choose(value: string) {
  sendAnswer('', value)
}
</script>

<style scoped>
.blk-question {
  border: 1px solid var(--bg-3); border-radius: var(--r-md);
  padding: var(--sp-3); background: var(--bg-1);
}
.q-title { font-size: var(--fs-xs); color: var(--text-3); margin-bottom: var(--sp-1); }
.q-text { margin: 0 0 var(--sp-2); font-size: var(--fs-sm); color: var(--text-1); line-height: 1.5; }
/* 窄容器自适应：悬浮面板仅 368px，多个长选项一行排不下 —— 允许换行逐行排，
   否则行溢出被父级 overflow:hidden 裁切、相邻按钮文字互相压盖（修「悬浮窗的问题
   选择栏布局混乱没有适应小窗口」）。按钮保持 nowrap 的完整 label（语音精确匹配接口）。
   Narrow-container adaptation: the float panel is only 368px wide and several long
   options cannot fit one row — allow wrapping so they lay out line by line; otherwise
   the row overflows, gets clipped by the parent's overflow:hidden, and adjacent
   button labels overwrite each other (fixes "the float window's question option bar
   is scrambled on small windows"). Buttons keep their nowrap full labels (the
   exact-match speech interface). */
.q-row { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-2); }
/* 输入框占满剩余行宽。Input fills the remaining row width. */
.q-row :deep(.q-input) { flex: 1; min-width: 0; }
.q-answered .q-label { color: var(--text-3); font-size: var(--fs-sm); }
</style>
