<template>
  <!-- 开始页语音设置迷你卡：引擎选择（本地/API）+ 角色选择 + 试听。
       Start-page voice settings mini card: engine picker (local/API) + voice selection + preview. -->
  <div class="tts-mini">
    <!-- 引擎选择（与控制台「语音合成」卡1 同一单例，改动双向同步）。
         Engine choice (same singleton as the console TTS card 1; changes sync both ways). -->
    <UiSegmented
      :model-value="engine"
      :options="ENGINE_OPTIONS"
      aria-label="语音引擎"
      @update:model-value="v => setEngine(v as TtsEngine)"
    />
    <!-- 选了 API 但后端未配置：给引导（不阻止选择，配置入口在控制台）。
         API chosen but backend unconfigured: guidance only (config lives in the console). -->
    <p v-if="engine === 'api' && !apiAvailable" class="tm-hint">API 语音需在控制台「语音合成」中配置</p>

    <!-- 角色选择 + 试听/停止（播报中停止按钮替换试听，可打断预览与正式播报）。 -->
    <div class="tm-row">
      <VoiceSelect class="tm-voice" label="角色" />
      <UiButton
        v-if="speaking"
        class="tm-test"
        variant="secondary"
        size="sm"
        @click="stopSpeak('ui')"
      >
        <UiIcon name="stop" :size="12" /> 停止
      </UiButton>
      <UiButton v-else class="tm-test" variant="secondary" size="sm" @click="testVoice()">
        <UiIcon name="play" :size="12" /> 试听
      </UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 开始页语音设置迷你卡。
 * Start-page voice settings mini card.
 *
 * 引擎选择复用 useTtsEngine 单例（与控制台「语音合成」卡1 同源），
 * 角色选择复用 VoiceSelect（与 TtsSettings 同一实现）。
 * Engine choice reuses the useTtsEngine singleton (shared with the console
 * TTS card 1); voice selection reuses VoiceSelect (same as TtsSettings).
 */
import { UiSegmented, UiButton, UiIcon } from '../ui'
import type { SegOption } from '../ui'
import type { TtsEngine } from '../../composables/assistant/useTts'
import VoiceSelect from './VoiceSelect.vue'
import { speaking, stopSpeak, testVoice } from '../../composables/assistant/useTts'
import { useTtsEngine } from '../../composables/assistant/useTtsEngine'

/** 引擎选项（与 UiSegmented 契约）。Engine options (UiSegmented contract). */
const ENGINE_OPTIONS: SegOption[] = [
  { value: 'browser', label: '本地语音' },
  { value: 'api', label: 'API 语音' },
]

/** 引擎选择单例（本地 / API）。Engine choice singleton (local / API). */
const { engine, apiAvailable, setEngine } = useTtsEngine()
</script>

<style scoped>
/* 迷你卡容器。Mini card container. */
.tts-mini { display: flex; flex-direction: column; gap: 12px; }

/* API 未配置引导。API-unconfigured guidance. */
.tm-hint {
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.5; margin: 0;
  background: rgba(251, 191, 36, .06);
  border: 1px dashed rgba(251, 191, 36, .3);
  border-radius: var(--r-sm); padding: 6px 8px;
}

/* 角色行：左选择器右试听。Voice row: picker left, preview right. */
.tm-row { display: flex; align-items: flex-end; gap: 8px; }
.tm-voice { flex: 1; min-width: 0; }
</style>
