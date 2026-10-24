<template>
  <!-- 模型配置卡：模型选择 + Schema 参数 + 恢复默认。VAD/KWS/ASR/TTS 复用。
       Model config card: model picker + schema params + reset-to-default. Reused by
       VAD/KWS/ASR/TTS. -->
  <SettingsCard :title="titleZh" :title-en="titleEn">
    <template #actions>
      <UiButton variant="ghost" size="sm" @click="resetModel">
        <BiLabel zh="恢复默认" en="Reset" />
      </UiButton>
    </template>

    <SettingsField label="模型" en="Model">
      <UiSelect
        :model-value="modelValue"
        :options="modelOptions"
        :placeholder="placeholder"
        @update:model-value="v => emit('update:model', String(v))"
      />
      <p v-if="missingHint" class="cs-hint">{{ missingHint }}</p>
    </SettingsField>

    <SchemaForm :params="params" :values="values" @change="emit('change')" />
  </SettingsCard>
</template>

<script setup lang="ts">
/**
 * 模型配置卡：只负责「选哪个模型 + 模型参数 + 恢复默认」。来源模式（本地/API）与
 * 供应商由外层 SourceModeSwitch / ModelProviderPanel 处理。
 *
 * Model config card owns "which model + its params + reset"; the source mode (local/API)
 * and providers live in SourceModeSwitch / ModelProviderPanel.
 */
import SettingsCard from './SettingsCard.vue'
import SettingsField from './SettingsField.vue'
import SchemaForm, { type SchemaField } from './SchemaForm.vue'
import BiLabel from './BiLabel.vue'
import { UiButton, UiSelect } from '../../ui'
import type { SegOption } from '../../ui/UiSegmented.vue'

const props = withDefaults(defineProps<{
  kind: string
  titleZh: string
  titleEn?: string
  modelValue: string
  modelOptions: SegOption[]
  values: Record<string, any>
  params: SchemaField[]
  placeholder?: string
  missingHint?: string
}>(), {
  titleEn: '',
  placeholder: '选择模型 / Select model',
  missingHint: '',
})

const emit = defineEmits<{ 'update:model': [v: string]; change: []; reset: [] }>()

/** 把模型专属参数重置为 schema 默认值（通用参数 provider/线程不动）。
 *  Reset model-specific params to schema defaults (common provider/threads untouched). */
function resetModel() {
  for (const f of props.params) {
    if ((f.group || 'model') !== 'model') continue
    props.values[f.key] = f.default
  }
  emit('reset')
}
</script>

<style scoped>
.cs-hint { font-size: var(--fs-2xs); color: var(--text-3); margin: var(--sp-q6) 0 0; line-height: 1.5; }
</style>
