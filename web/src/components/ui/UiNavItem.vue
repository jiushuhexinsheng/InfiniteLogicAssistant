<template>
  <button class="ui-nav-item" :class="{ active }" type="button" @click="$emit('click')">
    <UiIcon v-if="icon" :name="icon" :size="15" />
    <span class="ui-nav-label"><slot>{{ label }}</slot></span>
    <span v-if="badge" class="ui-nav-badge">{{ badge }}</span>
  </button>
</template>

<script setup lang="ts">
import UiIcon from './UiIcon.vue'
withDefaults(defineProps<{ label?: string; icon?: string; active?: boolean; badge?: string | number }>(), { label: '', icon: '', active: false, badge: undefined })
defineEmits<{ click: [] }>()
</script>

<style scoped>
.ui-nav-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 8px 12px; border: none; border-radius: var(--r-md);
  background: none; color: var(--text-2); font-family: inherit; font-size: var(--fs-sm);
  cursor: pointer; text-align: left;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.ui-nav-item:hover { background: var(--surface-control); color: var(--text-1); }
.ui-nav-item.active {
  background: var(--brand-grad); color: var(--text-on-brand); font-weight: 600;
  box-shadow: 0 4px 14px -4px rgba(103, 232, 249, .5);
}
.ui-nav-badge {
  margin-left: auto; font-family: var(--font-mono); font-size: 10px;
  color: var(--text-3);
}
.ui-nav-item.active .ui-nav-badge { color: var(--text-on-brand); opacity: .7; }
</style>
