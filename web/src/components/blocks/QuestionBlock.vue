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
        <button
          v-for="opt in block.payload.options"
          :key="opt.value"
          class="q-btn"
          :class="{ primary: opt.value === 'yes' }"
          @click="choose(opt.value)"
        >{{ opt.label }}</button>
      </div>
      <!-- choice 下不渲染输入框：自由文本会被后端判为未选择而拒绝。
           No input for choice: free text is rejected as "no selection" by the backend. -->
      <div v-if="allowText" class="q-row">
        <input
          v-model="text"
          class="q-input"
          placeholder="输入回答后回车…"
          @keydown.enter="submit"
        />
        <button class="q-btn" @click="submit">回答</button>
      </div>
    </template>
    <div v-else class="q-answered">
      <span class="q-label">❓ {{ block.payload.question }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
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
.q-row { display: flex; gap: var(--sp-2); margin-top: var(--sp-2); }
.q-btn {
  min-height: var(--min-target-size, 44px); padding: 0 var(--sp-3);
  border-radius: var(--r-md); border: 1px solid var(--bg-3);
  background: var(--bg-2); color: var(--text-1); cursor: pointer;
  font-size: var(--fs-sm);
}
.q-btn.primary { background: var(--brand-c2); border-color: var(--brand-c2); color: var(--text-on-brand); }
.q-btn:focus-visible, .q-input:focus-visible {
  outline: 2px solid var(--focus-ring, var(--brand-c2)); outline-offset: var(--focus-offset, 2px);
}
.q-input {
  flex: 1; min-height: var(--min-target-size, 44px); padding: 0 var(--sp-2);
  border-radius: var(--r-md); border: 1px solid var(--bg-3);
  background: var(--bg-2); color: var(--text-1); font-size: var(--fs-sm);
}
.q-answered .q-label { color: var(--text-3); font-size: var(--fs-sm); }
</style>
