<template>
  <!-- 可编辑模型表格：一行一个模型（combobox，可输可选），底部新增。
       Editable model table: one combobox row per model (type or pick), add at the bottom. -->
  <div class="model-table">
    <div v-for="(row, i) in rows" :key="i" class="mt-row">
      <UiCombobox
        :model-value="row"
        :options="options"
        placeholder="model-id"
        @update:model-value="v => updateRow(i, String(v))"
      />
      <SettingsButton
        variant="secondary" hover="danger" class="mt-del"
        zh="删除" en="Delete" @click="removeRow(i)"
      />
    </div>
    <p v-if="!rows.length" class="mt-empty">尚未添加模型</p>
    <SettingsButton variant="secondary" class="mt-add" zh="添加模型" en="Add model" @click="addRow" />
  </div>
</template>

<script setup lang="ts">
/**
 * 模型表格：内部保留编辑中的原始行（可暂时为空），对外只发出去空去重后的列表。
 * `props.models` 被外部改写（如拉取后整体替换）时同步回内部行。
 *
 * Model table: keeps raw rows internally (a row may be empty while being typed) and
 * emits a trimmed, de-duplicated list; external `props.models` changes resync the rows.
 */
import { nextTick, ref, watch } from 'vue'
import { UiCombobox } from '../../ui'
import SettingsButton from './SettingsButton.vue'

const props = withDefaults(defineProps<{
  models: string[]
  options?: string[]
}>(), { options: () => [] })

const emit = defineEmits<{ 'update:models': [v: string[]] }>()

const rows = ref<string[]>([...props.models])

/** 去空、trim、去重（大小写敏感），保持顺序。Clean the list before emitting. */
function clean(list: string[]): string[] {
  const out: string[] = []
  for (const raw of list) {
    const value = raw.trim()
    if (value && !out.includes(value)) out.push(value)
  }
  return out
}

/** 发出当前合法模型列表。Emit the current valid model list. */
function emitModels(): void {
  emit('update:models', clean(rows.value))
}

/** 改一行。Edit one row. */
function updateRow(index: number, value: string): void {
  rows.value[index] = value
  emitModels()
}

/** 删一行。Remove one row. */
function removeRow(index: number): void {
  rows.value.splice(index, 1)
  emitModels()
}

/** 追加空行并聚焦。Append an empty row and focus it. */
async function addRow(): Promise<void> {
  rows.value.push('')
  await nextTick()
  const inputs = document.querySelectorAll<HTMLInputElement>('.model-table .mt-row .ui-input')
  inputs[inputs.length - 1]?.focus()
}

// 外部整表替换（拉取后批量添加/父组件回写）时同步；与内部清理结果一致则不动，
// 以免正在输入的空行被父组件的清理结果冲掉。
watch(() => props.models, value => {
  if (JSON.stringify(value) !== JSON.stringify(clean(rows.value))) rows.value = [...value]
}, { deep: true })
</script>

<style scoped>
.model-table { display: flex; flex-direction: column; gap: var(--sp-2); }
.mt-row { display: flex; align-items: center; gap: var(--sp-2); }
.mt-row :deep(.ui-combo) { flex: 1; min-width: 0; }
.mt-empty { margin: 0; font-size: var(--fs-2xs); color: var(--text-3); }
.mt-add { align-self: flex-start; }
</style>
