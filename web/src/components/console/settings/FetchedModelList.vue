<template>
  <!-- 拉取结果列表：未添加项可勾选；全选/反选只作用于未添加项；「添加所选」一次性回传。
       Fetched-model list: only not-yet-added models are selectable; select-all/invert
       operate on those; "add selected" emits them in one go. -->
  <div class="fetched-list">
    <div class="fm-head">
      <span class="fm-count">共 {{ models.length }} 个，未添加 {{ available.length }} 个</span>
      <div class="fm-actions">
        <SettingsButton variant="ghost" class="fm-all" zh="全选" en="All" @click="selectAll" />
        <SettingsButton variant="ghost" class="fm-invert" zh="反选" en="Invert" @click="invert" />
        <SettingsButton
          variant="secondary" class="fm-add" :disabled="!picked.length"
          :zh="`添加所选${picked.length ? `（${picked.length}）` : ''}`" en="Add selected"
          @click="addPicked"
        />
      </div>
    </div>
    <div class="fm-rows">
      <label v-for="m in models" :key="m" class="fm-row" :class="{ added: isAdded(m) }">
        <input
          type="checkbox"
          :checked="picked.includes(m)"
          :disabled="isAdded(m)"
          @change="toggle(m, ($event.target as HTMLInputElement).checked)"
        />
        <span class="fm-name">{{ m }}</span>
        <span v-if="isAdded(m)" class="fm-tag">已添加</span>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 拉取结果复选列表。Fetched-model checkbox list. */
import { computed, ref } from 'vue'
import SettingsButton from './SettingsButton.vue'

const props = withDefaults(defineProps<{
  models: string[]
  added?: string[]
}>(), { added: () => [] })

const emit = defineEmits<{ add: [models: string[]] }>()

/** 当前勾选（只存未添加项）。Current picks (not-yet-added only). */
const picked = ref<string[]>([])

/** 是否已添加。Whether a model is already added. */
function isAdded(model: string): boolean {
  return props.added.includes(model)
}

/** 未添加项。Models not yet added. */
const available = computed(() => props.models.filter(m => !isAdded(m)))

/** 勾选/取消一项。Toggle one model. */
function toggle(model: string, checked: boolean): void {
  if (isAdded(model)) return
  picked.value = checked
    ? [...picked.value, model]
    : picked.value.filter(m => m !== model)
}

/** 全选未添加项。Select every available model. */
function selectAll(): void {
  picked.value = [...available.value]
}

/** 反选未添加项。Invert the available selection. */
function invert(): void {
  picked.value = available.value.filter(m => !picked.value.includes(m))
}

/** 回传所选并清空勾选。Emit the picks and clear them. */
function addPicked(): void {
  if (!picked.value.length) return
  emit('add', [...picked.value])
  picked.value = []
}
</script>

<style scoped>
.fetched-list { border: 1px solid var(--border-soft); border-radius: var(--r-sm); padding: var(--sp-2); }
.fm-head { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2); margin-bottom: var(--sp-2); }
.fm-count { font-size: var(--fs-2xs); color: var(--text-3); }
.fm-actions { display: flex; align-items: center; gap: var(--sp-1); }
.fm-rows { max-height: 180px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.fm-row { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-2xs); color: var(--text-2); padding: 2px var(--sp-1); border-radius: var(--r-sm); cursor: pointer; }
.fm-row:hover:not(.added) { background: rgba(103, 232, 249, .06); }
.fm-row.added { opacity: .55; cursor: not-allowed; }
.fm-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fm-tag { color: var(--text-3); }
</style>
