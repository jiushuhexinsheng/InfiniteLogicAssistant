<template>
  <!-- 代码模块：语言标签 + 复制按钮（本轮无高亮依赖，避免引包）。
       Code block: language tag + copy button (no highlight dependency this round). -->
  <div class="blk-code" :class="skin">
    <div class="code-head">
      <span class="code-lang">{{ block.payload.language || 'text' }}</span>
      <span v-if="block.payload.filename" class="code-file">{{ block.payload.filename }}</span>
      <UiIconButton :title="copied ? '已复制' : '复制'" compact @click="copy">
        <UiIcon :name="copied ? 'check' : 'copy'" :size="11" />
      </UiIconButton>
    </div>
    <pre class="code-body"><code>{{ block.payload.code }}</code></pre>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { UiIconButton, UiIcon } from '../ui'
import type { Block, Skin } from '../../blocks/types'

/**
 * 组件属性定义。Component props definition.
 * @property block - 代码块。Code block.
 * @property skin - 渲染皮肤。Render skin.
 */
const props = defineProps<{ block: Block; skin?: Skin }>()

/** 复制成功短暂状态。Brief copied state. */
const copied = ref(false)
let copiedTimer: ReturnType<typeof setTimeout> | null = null

/** 复制代码到剪贴板，成功后短暂显示对勾。Copy code to clipboard with a brief check mark. */
async function copy() {
  try {
    await navigator.clipboard.writeText(String(props.block.payload.code || ''))
    copied.value = true
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => { copied.value = false }, 1500)
  } catch { /* 剪贴板不可用时忽略 */ }
}
</script>

<style scoped>
.blk-code {
  border: 1px solid var(--border-soft, var(--bg-3)); border-radius: var(--r-md);
  overflow: hidden; background: rgba(2, 6, 23, .55);
}
.code-head {
  display: flex; align-items: center; gap: var(--sp-2);
  padding: var(--sp-1) var(--sp-2);
  background: var(--bg-2); font-size: var(--fs-xs); color: var(--text-3);
}
.code-lang { font-family: var(--font-mono); }
.code-file { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.code-body {
  margin: 0; padding: var(--sp-2) var(--sp-3); overflow-x: auto;
  font-family: var(--font-mono); font-size: var(--fs-xs); line-height: 1.55;
  color: var(--text-1);
}
</style>
