<template>
  <!-- 音色选择（API 引擎）：点开即选，voiceclone 模型由后端 voice_ref 决定仅显示说明。
       Voice picker (API): open-to-pick; voiceclone models are backend-decided. -->
  <div class="voice-select">
    <span class="vs-label">{{ label }}<em v-if="engine === 'api'">API</em></span>
    <!-- voiceclone：声音由后端参考音频决定，无需前端选。Voiceclone: backend decides the voice. -->
    <p v-if="isVoiceClone" class="vs-clone">克隆 voice_ref 参考音频（控制台「参考音频」字段配置）</p>
    <UiSelect v-else v-model="ttsSettings.apiVoice" :options="apiVoiceItems" @update:model-value="saveTts()" />
  </div>
</template>

<!-- 公共音色选择：TtsSettings 与 TtsMini 共用（同一单例、同一持久化逻辑）。Shared voice picker: used by both TtsSettings and TtsMini. -->
<script setup lang="ts">
import { computed } from 'vue'
import { UiSelect } from '../ui'
import type { SegOption } from '../ui/UiSegmented.vue'
import { ttsSettings, saveTts, API_VOICE_SUGGESTIONS } from '../../composables/assistant/useTts'
import { useTtsEngine } from '../../composables/assistant/useTtsEngine'
import { useConfig } from '../../composables/useApi'

/** 组件 Props：标签。Component props: label. */
withDefaults(defineProps<{
  label?: string
}>(), { label: '音色' })

/** 引擎选择单例。Engine choice singleton. */
const { engine } = useTtsEngine()

/** 全局配置。Global config. */
const app = useConfig()

/** 是否 voiceclone 模型。Whether the model is voiceclone. */
const isVoiceClone = computed(() =>
  (app.config.value?.tts_model || '').toLowerCase().includes('voiceclone')
)

/**
 * API 音色候选：后端默认 voice + 预置音色；
 * 当前值是历史自定义名时插到最前，保证可见、可回选（下拉形态不再支持自由输入，
 * 自定义音色的编辑入口在合成卡「音色」字段——那是后端 profile 配置）。
 *
 * API voice candidates: backend default + presets; a historical custom value is
 * prepended so it stays visible/selectable (the dropdown form drops free typing —
 * custom voices are edited in the synthesis card's "voice" field).
 */
const voiceOptions = computed(() => {
  const cfg = app.config.value?.tts_voice
  const list = [...API_VOICE_SUGGESTIONS]
  if (cfg && !list.includes(cfg)) list.unshift(cfg)
  const cur = ttsSettings.value.apiVoice
  if (cur && !list.includes(cur)) return [cur, ...list]
  return list
})

/** API 引擎的音色下拉选项（含「默认音色」空值项，空值 = 走后端配置）。 */
const apiVoiceItems = computed<SegOption[]>(() => [
  { value: '', label: '默认音色（后端配置）' },
  ...voiceOptions.value.map(s => ({ value: s, label: s })),
])
</script>

<style scoped>
.voice-select { display: flex; flex-direction: column; gap: var(--sp-q6); min-width: 0; }
/* 标签：API 引擎时带后缀徽标。Label: suffixed with a badge on the API engine. */
.vs-label {
  font-size: var(--fs-2xs); color: var(--text-3);
  display: flex; justify-content: space-between; align-items: baseline;
}
.vs-label em {
  font-style: normal; font-family: var(--font-mono);
  color: var(--brand-c2); font-size: var(--fs-2xs);
}

/* voiceclone 说明。Voiceclone note. */
.vs-clone {
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.5; margin: 0;
  background: rgba(103, 232, 249, .06);
  border: 1px dashed rgba(103, 232, 249, .25);
  border-radius: var(--r-sm); padding: var(--sp-q6) var(--sp-2);
}
</style>
