<template>
  <!-- 来源模式：本地 / API（按能力可扩展为 3 项）。Source mode: local / API (3 options allowed). -->
  <div class="source-mode">
    <span class="sm-label">
      <b>{{ labelZh }}</b>
      <i>{{ labelEn }}</i>
    </span>
    <UiSegmented
      :model-value="modelValue"
      :options="opts"
      :aria-label="labelZh"
      @update:model-value="v => emit('update:modelValue', String(v))"
    />
  </div>
</template>

<script setup lang="ts">
/** 本地/API 来源切换器（VAD/KWS/ASR/TTS 共用）。Shared local/API source switch. */
import { computed } from 'vue'
import { UiSegmented } from '../../ui'

interface ModeOption {
  value: string
  label: string
  en?: string
}

const props = withDefaults(defineProps<{
  modelValue: string
  options?: ModeOption[]
  labelZh?: string
  labelEn?: string
}>(), {
  options: () => [
    { value: 'local', label: '本地', en: 'Local' },
    { value: 'api', label: 'API', en: 'API' },
  ],
  labelZh: '来源',
  labelEn: 'Source',
})

const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

const opts = computed(() => props.options.map(o => ({
  value: o.value,
  label: o.en ? `${o.label} / ${o.en}` : o.label,
})))
</script>

<style scoped>
.source-mode {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--sp-3); padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  background: rgba(15, 23, 42, .45);
}
.sm-label { display: flex; align-items: baseline; gap: var(--sp-q6); font-size: var(--fs-2xs); color: var(--text-3); }
.sm-label b { color: var(--text-2); font-weight: 500; }
.sm-label i { font-style: normal; opacity: .7; }
</style>
