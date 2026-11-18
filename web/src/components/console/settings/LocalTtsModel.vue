<template>
  <!-- 本地 TTS：引擎选择在合成 Tab 顶部，这里只配置 Kokoro 模型与推理硬件。
       Local TTS: engine choice lives at the top of the synthesis tab; this block only
       configures the Kokoro model and its inference hardware. -->
  <p class="cs-hint">引擎选择（本地 Kokoro / API）在「合成」Tab 顶部；这里配置本地 Kokoro 的模型与推理硬件。</p>
  <ModelConfigCard
    v-if="ttsSettings.engine === 'local'"
    kind="tts" title-zh="本地 TTS 模型" title-en="Local TTS"
    :model-value="s.ed().tts.local_model"
    :model-options="modelOptions('tts')"
    :values="s.ed().tts"
    :params="schemaFor('tts')"
    :missing-hint="missingHint('tts', s.ed().tts.local_model)"
    placeholder="选择 TTS 模型 / Select TTS model"
    @update:model="v => switchModel('tts', v)"
  />
</template>

<script setup lang="ts">
/**
 * 本地 TTS 模型段，从 LocalModelsCard 拆出。
 * Local TTS model section, extracted from LocalModelsCard.
 */
import ModelConfigCard from './ModelConfigCard.vue'
import { ttsSettings } from '../../../composables/assistant/useTts'
import { useSettings } from './useSettings'
import { useLocalModels } from './useLocalModels'

const s = useSettings()
const { modelOptions, missingHint, schemaFor, switchModel } = useLocalModels()
</script>

<style scoped>
.cs-hint { font-size: var(--fs-2xs); color: var(--text-3); margin: var(--sp-q6) 0 0; line-height: 1.5; }
</style>
