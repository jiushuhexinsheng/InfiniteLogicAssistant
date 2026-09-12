<template>
  <div v-if="error" class="ui-errnote">{{ error }}</div>
</template>

<!-- 内联错误提示：统一的加载失败展示样式。Inline error note: unified load-failure display. -->
<script setup lang="ts">
/** 组件 props：错误文案（空则不渲染）。Component props: error text (nothing renders when empty). */
defineProps<{ error: string | null | undefined }>()
</script>

<style scoped>
.ui-errnote {
  font-size: var(--fs-xs); color: var(--err);
  background: rgba(248, 113, 113, .07);
  border: 1px solid rgba(248, 113, 113, .3);
  border-radius: var(--r-sm); padding: 7px 10px;
}
</style>
