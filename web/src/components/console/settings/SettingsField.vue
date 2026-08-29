<template>
  <component :is="row ? 'div' : 'label'" class="sf" :class="{ row, grow }">
    <span class="sf-label">{{ label }}</span>
    <span class="sf-control"><slot /></span>
  </component>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ label: string; row?: boolean; grow?: boolean }>(), { row: false, grow: false })
</script>

<style scoped>
.sf { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.sf.row { flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; }
.sf.grow { flex: 1; }
.sf-label { font-size: var(--fs-2xs); color: var(--text-3); flex-shrink: 0; }
.sf-control { min-width: 0; display: block; }
</style>
