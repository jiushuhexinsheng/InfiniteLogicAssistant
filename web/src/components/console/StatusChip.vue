<template>
  <span class="status-chip" :class="available ? 'ok' : 'no'">
    <span class="dot"></span>
    <span class="label">{{ label }}</span>
    <span v-if="detail" class="detail">{{ detail }}</span>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  available: boolean
  detail?: string
}>()
</script>

<style scoped>
.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  border: 1px solid var(--border-base);
  border-radius: 999px;
  padding: 3px 10px;
  color: var(--text-2);
  background: rgba(30, 41, 59, .6);
}
.dot { width: 7px; height: 7px; border-radius: 50%; }
.status-chip.ok .dot { background: #34d399; box-shadow: 0 0 6px #34d399; }
.status-chip.no .dot { background: #f87171; box-shadow: 0 0 6px #f87171; }
.label { color: var(--text-1); }
.detail { color: var(--text-3); font-size: 11px; }
</style>
