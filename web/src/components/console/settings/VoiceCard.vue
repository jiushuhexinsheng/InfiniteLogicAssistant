<template>
  <!-- 语音模块：唤醒词 + VAD + 本地播报配置。Voice module: wake word + VAD + local speech settings. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">语音（唤醒 / 静音检测）</span>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule('voice')">
        {{ s.saving.value ? '保存中…' : '保存' }}
      </UiButton>
    </div>
    <SettingsField v-if="s.editable.value" label="唤醒启用" row>
      <UiToggle :model-value="s.ed().wake_word.enabled" @update:model-value="v => (s.ed().wake_word.enabled = v)" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="唤醒词">
      <UiInput v-model="s.ed().wake_word.keyword" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="灵敏度（0-1）">
      <UiInput type="number" step="0.05" min="0" max="1" :model-value="s.ed().wake_word.sensitivity" @update:model-value="v => (s.ed().wake_word.sensitivity = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="静音判定阈值">
      <UiInput type="number" step="0.01" :model-value="s.ed().vad.silence_threshold" @update:model-value="v => (s.ed().vad.silence_threshold = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="静音停止时长（ms）">
      <UiInput type="number" :model-value="s.ed().vad.silence_duration_ms" @update:model-value="v => (s.ed().vad.silence_duration_ms = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="最长录音（ms）">
      <UiInput type="number" :model-value="s.ed().vad.max_duration_ms" @update:model-value="v => (s.ed().vad.max_duration_ms = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="等待回答超时（ms）">
      <UiInput type="number" min="1" :model-value="s.ed().vad.answer_timeout_ms" @update:model-value="v => (s.ed().vad.answer_timeout_ms = toNum(v))" />
    </SettingsField>
    <div class="cs-tts"><TtsSettings /></div>
  </UiCard>
</template>

<!-- 语音模块卡：唤醒词 / VAD 参数 + 内嵌 TTS 设置。Voice module card: wake word / VAD params + embedded TTS settings. -->
<script setup lang="ts">
import TtsSettings from '../../assistant/TtsSettings.vue'
import SettingsField from './SettingsField.vue'
import { UiButton, UiCard, UiInput, UiToggle } from '../../ui'
import { useSettings } from './useSettings'

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/**
 * 数值输入：保留空串（清空），其余转 number（与原生 v-model.number 行为一致）。
 * Numeric input: keep the empty string (cleared), otherwise convert to number
 * (consistent with native v-model.number).
 *
 * @param v 输入框原值。The raw input value.
 * @returns 数值或空串。The number, or an empty string.
 */
function toNum(v: string): number | '' {
  return v === '' ? '' : Number(v)
}
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}
.cs-tts { margin-top: 2px; }
</style>
