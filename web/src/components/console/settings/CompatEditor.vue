<template>
  <!-- 高级兼容编辑器：键值行 + 新增；快捷项并入键 combobox，不再单列 chip。
       Advanced compat editor: key/value rows + add; shortcuts live as options of the
       key combobox instead of a separate chip row. -->
  <div class="compat-editor">
    <p class="ce-hint">特殊网关的请求体补丁；键可直接选内置项或手输。</p>
    <CompatRow
      v-for="(row, i) in rows"
      :key="i"
      :entry="row"
      :key-options="keyOptions"
      @update:key="v => setKey(i, v)"
      @update:value="v => setValue(i, v)"
      @remove="remove(i)"
    />
    <SettingsButton variant="secondary" class="cr-add" zh="新增兼容键" en="Add compat key" @click="add" />
  </div>
</template>

<script setup lang="ts">
/** 兼容键值编辑器（受控：entries 进，update 出）。Controlled compat editor. */
import { computed, ref, watch } from 'vue'
import SettingsButton from './SettingsButton.vue'
import CompatRow from './CompatRow.vue'
import { COMPAT_SHORTCUTS } from './profiles'

const props = withDefaults(defineProps<{ entries?: Array<[string, string]> }>(), {
  entries: () => [],
})

const emit = defineEmits<{ update: [entries: Array<[string, string]>] }>()

/** 内部行（编辑中）；外部 entries 变更时同步。Internal rows, resynced from props. */
const rows = ref<Array<[string, string]>>(props.entries.map(([k, v]) => [k, v]))
watch(() => props.entries, value => {
  rows.value = value.map(([k, v]) => [k, v] as [string, string])
}, { deep: true })

/** 键候选 = 内置快捷键。Key options = built-in shortcut keys. */
const keyOptions = computed(() => COMPAT_SHORTCUTS.map(c => c.key))

/** 复制当前行。Copy the rows. */
function copyRows(): Array<[string, string]> {
  return rows.value.map(([k, v]) => [k, v] as [string, string])
}

/** 改键：命中内置键时带出默认值，手输键保留原值。Change a key. */
function setKey(index: number, key: string): void {
  const next = copyRows()
  const shortcut = COMPAT_SHORTCUTS.find(c => c.key === key)
  next[index] = [key, shortcut ? shortcut.value : next[index][1]]
  rows.value = next
  emit('update', next)
}

/** 改值。Change a value. */
function setValue(index: number, value: string): void {
  const next = copyRows()
  next[index] = [next[index][0], value]
  rows.value = next
  emit('update', next)
}

/** 删行。Remove a row. */
function remove(index: number): void {
  const next = copyRows()
  next.splice(index, 1)
  rows.value = next
  emit('update', next)
}

/** 新增空行（占位键名，改名即生效）。Add an empty row. */
function add(): void {
  const next: Array<[string, string]> = [...copyRows(), [`key_${Date.now().toString(36)}`, '']]
  rows.value = next
  emit('update', next)
}
</script>

<style scoped>
.compat-editor { display: flex; flex-direction: column; gap: var(--sp-2); }
.ce-hint { margin: 0; font-size: var(--fs-2xs); color: var(--text-3); }
.cr-add { align-self: flex-start; }
</style>
