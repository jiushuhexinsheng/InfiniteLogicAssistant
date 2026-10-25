<template>
  <!-- 获取模型弹窗：搜索 + 复选列表；「添加所选」回传后自动关闭。
       Fetched-model dialog: search + checkbox list; "add selected" emits and closes. -->
  <UiModal :model-value="modelValue" title="选择要添加的模型 / Select models"
           @update:model-value="v => emit('update:modelValue', v)">
    <div class="fmd">
      <input v-model="query" class="fmd-search" type="text" placeholder="搜索模型… / Search" />
      <FetchedModelList :models="filtered" :added="added" @add="onAdd" />
      <p v-if="!filtered.length" class="fmd-empty">没有匹配的模型</p>
    </div>
  </UiModal>
</template>

<script setup lang="ts">
/** 拉取结果的弹窗容器（列表本体仍是 FetchedModelList）。Dialog wrapper around the list. */
import { computed, ref } from 'vue'
import { UiModal } from '../../ui'
import FetchedModelList from './FetchedModelList.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  models: string[]
  added?: string[]
}>(), { added: () => [] })

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  add: [models: string[]]
}>()

const query = ref('')

/** 搜索过滤（按模型 id 子串）。Filter by model-id substring. */
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? props.models.filter(m => m.toLowerCase().includes(q)) : props.models
})

/** 回传所选并关闭。Emit picks and close. */
function onAdd(picked: string[]): void {
  emit('add', picked)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.fmd { display: flex; flex-direction: column; gap: var(--sp-2); min-height: 240px; }
.fmd-search {
  width: 100%; box-sizing: border-box; padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  background: rgba(15, 23, 42, .7); color: var(--text-1); font-size: var(--fs-2xs); outline: none;
}
.fmd-search:focus { border-color: var(--brand-c2); }
.fmd-empty { margin: 0; font-size: var(--fs-2xs); color: var(--text-3); text-align: center; padding: var(--sp-3); }
.fmd :deep(.fm-rows) { max-height: 320px; }
</style>
