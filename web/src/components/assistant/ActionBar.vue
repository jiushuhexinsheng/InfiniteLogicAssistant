<template>
  <div class="panel-actions">
    <button class="act-btn" title="清空对话" @click="emit('clear')">🗑</button>
    <button class="act-btn" title="收起" @click="emit('close')">▼</button>
  </div>
</template>

<script setup lang="ts">
const emit = defineEmits<{ clear: []; close: [] }>()
</script>

<style scoped>
.panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding: 8px 14px;
  border-top: 1px solid var(--border-base);
}
.act-btn {
  background: #334155;
  border: 1px solid transparent;
  color: var(--text-2);
  font-size: 16px;
  padding: 4px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all .2s;
}
.act-btn:hover {
  /* hover 品牌渐变描边 */
  background: linear-gradient(#334155, #334155) padding-box, var(--brand-grad) border-box;
  color: var(--text-1);
}
</style>
