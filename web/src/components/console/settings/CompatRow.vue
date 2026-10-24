<template>
  <!-- 兼容键值行：键为可输可选 combobox，值为普通输入。Compat key/value row. -->
  <div class="cr-row">
    <UiCombobox
      :model-value="entry[0]"
      :options="keyOptions"
      placeholder="键"
      @update:model-value="v => emit('update:key', String(v))"
    />
    <UiInput
      :model-value="entry[1]"
      placeholder="值"
      @update:model-value="v => emit('update:value', String(v))"
    />
    <UiButton variant="secondary" size="sm" hover="danger" class="cr-del" @click="$emit('remove')">
      删除
    </UiButton>
  </div>
</template>

<script setup lang="ts">
/** 单条兼容键值行。One compat key/value row. */
import { UiButton, UiCombobox, UiInput } from '../../ui'

withDefaults(defineProps<{
  entry: [string, string]
  keyOptions?: string[]
}>(), { keyOptions: () => [] })

const emit = defineEmits<{ 'update:key': [v: string]; 'update:value': [v: string]; remove: [] }>()
</script>

<style scoped>
.cr-row { display: flex; align-items: center; gap: var(--sp-2); }
.cr-row :deep(.ui-combo), .cr-row :deep(.ui-input) { flex: 1; min-width: 0; font-family: var(--font-mono); }
</style>
