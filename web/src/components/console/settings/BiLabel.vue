<template>
  <!-- 双语标签：中文主标签 + 英文小号副标签（同一行，避免两套字号打架）。
       Bilingual label: Chinese primary + small English secondary on one line. -->
  <span class="bi-label" :class="{ block }">
    <span class="bi-zh">{{ zh }}</span>
    <span v-if="en" class="bi-en">{{ en }}</span>
  </span>
</template>

<script setup lang="ts">
/** 中文主标签 / 英文副标签；`block` 时英文换行显示。Bilingual label; `block` puts English on its own line. */
withDefaults(defineProps<{ zh: string; en?: string; block?: boolean }>(), {
  en: '',
  block: false,
})
</script>

<style scoped>
.bi-label { display: inline-flex; align-items: baseline; gap: var(--sp-q6); min-width: 0; }
.bi-label.block { flex-direction: column; gap: 1px; }
.bi-zh { color: inherit; }
.bi-en {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  font-weight: 400;
  letter-spacing: .02em;
  white-space: nowrap;
}
</style>
