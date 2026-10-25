<template>
  <!-- 双语标签：inline = 中文主标签 + 英文小号副标签同一行；stack = 英文换到下一行。
       Bilingual label: inline puts the small English subtitle beside Chinese; stack puts
       it on the next line (narrow buttons / segmented options). English equal to Chinese
       is omitted in stack mode to avoid "API / API". -->
  <span class="bi-label" :class="[layout, { block }]">
    <span class="bi-zh">{{ zh }}</span>
    <span v-if="showEn" class="bi-en">{{ en }}</span>
  </span>
</template>

<script setup lang="ts">
/** 中文主标签 / 英文副标签；`stack`（或 `block`）时英文换行显示。 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  zh: string
  en?: string
  block?: boolean
  layout?: 'inline' | 'stack'
}>(), {
  en: '',
  block: false,
  layout: 'inline',
})

/** 是否实际渲染英文行（stack 下与中文完全相同则省略）。Whether to render English. */
const showEn = computed(() => {
  if (!props.en) return false
  const stacked = props.layout === 'stack' || props.block
  return !(stacked && props.en === props.zh)
})
</script>

<style scoped>
.bi-label { display: inline-flex; align-items: baseline; gap: var(--sp-q6); min-width: 0; }
.bi-label.stack, .bi-label.block { flex-direction: column; gap: 1px; align-items: center; }
.bi-zh { color: inherit; }
.bi-en {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  font-weight: 400;
  letter-spacing: .02em;
  white-space: nowrap;
  line-height: 1.1;
}
</style>
