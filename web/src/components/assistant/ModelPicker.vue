<template>
  <!-- 对话内全局模型切换器：按供应商分组的模型下拉。切换即写全局配置。 -->
  <UiGroupedSelect
    class="model-picker"
    :groups="groups"
    :model-value="selectedValue"
    :placeholder="loaded ? '未配置模型' : '加载模型…'"
    :disabled="!loaded || !groups.length"
    :searchable="true"
    @update:model-value="choose"
  />
</template>

<script setup lang="ts">
/**
 * 对话输入框旁的模型切换器。数据来自 `GET /api/llm/models`；选择后调用
 * `POST /api/llm/active-model`（专用端点，避免 PATCH 整段替换 profiles），
 * 成功后刷新清单与 `/api/config`（顶栏同步），失败 toast 并保持原选择。
 *
 * Chat model picker. Reads `GET /api/llm/models`; a selection calls the dedicated
 * `POST /api/llm/active-model`, then refreshes the catalogue and `/api/config` (header
 * sync). On failure it toasts and keeps the previous selection.
 */
import { computed, onMounted, ref } from 'vue'
import { UiGroupedSelect, type OptionGroup } from '../ui'
import { api } from '../../api'
import { useConfig } from '../../composables/useApi'
import { notify } from '../../composables/useToast'
import type { LlmActive } from '../../types'

/** 组合值分隔符（provider 与 model 都可能含普通字符）。Composite value separator. */
const SEP = '\u0000'

const app = useConfig()
const loaded = ref(false)
const active = ref<LlmActive>({ provider: '', model: '' })
const groups = ref<OptionGroup[]>([])

/** 当前选中值（provider + model）。Current composite selection. */
const selectedValue = computed(() =>
  active.value.provider ? `${active.value.provider}${SEP}${active.value.model}` : '')

/** 拉取分组清单。Fetch the grouped catalogue. */
async function load(): Promise<void> {
  try {
    const r = await api.getLlmModels()
    active.value = r.active || { provider: '', model: '' }
    groups.value = (r.groups || []).map(g => ({
      label: g.label || g.provider,
      options: (g.models || []).map(m => ({
        value: `${g.provider}${SEP}${m}`,
        label: m,
      })),
    }))
  } catch {
    groups.value = []
  } finally {
    loaded.value = true
  }
}

/** 选择一项：持久化全局模型。Pick a model and persist it globally. */
async function choose(value: string): Promise<void> {
  if (!value || value === selectedValue.value) return
  const [provider, model] = value.split(SEP)
  try {
    await api.setActiveModel(provider, model)
  } catch (e: any) {
    notify.err('切换模型失败：' + (e?.message || e))
    return
  }
  await load()
  void app.refreshConfig()
}

onMounted(load)
</script>

<style scoped>
.model-picker { max-width: 160px; }
</style>
