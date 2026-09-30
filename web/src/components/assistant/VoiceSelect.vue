<template>
  <!-- 角色选择（按引擎切换形态）：本地=系统语音下拉；API=音色下拉（点开即选，
       原 input+datalist 在 Chrome 中点击不弹候选、体验等同不可用）；
       voiceclone 模型由后端 voice_ref 决定，仅显示说明。
       Voice picker (shape per engine): local = system voice dropdown; API = voice
       dropdown (open-to-pick — the former input+datalist never pops on click in
       Chrome, effectively unusable); voiceclone models are backend-decided. -->
  <div class="voice-select">
    <span class="vs-label">{{ label }}<em v-if="engine === 'api'">API</em></span>

    <template v-if="engine === 'browser'">
      <UiSelect v-model="ttsSettings.voiceName" @update:model-value="saveTts()">
        <option value="">系统默认</option>
        <option v-for="v in voices" :key="v.name" :value="v.name">{{ v.name }}</option>
      </UiSelect>
    </template>

    <template v-else>
      <!-- voiceclone：声音由后端参考音频决定，无需前端选。Voiceclone: backend decides the voice. -->
      <p v-if="isVoiceClone" class="vs-clone">克隆 voice_ref 参考音频（控制台「参考音频」字段配置）</p>
      <UiSelect v-else v-model="ttsSettings.apiVoice" @update:model-value="saveTts()">
        <option value="">默认音色（后端配置）</option>
        <option v-for="s in voiceOptions" :key="s" :value="s">{{ s }}</option>
      </UiSelect>
    </template>
  </div>
</template>

<!-- 公共角色选择：TtsSettings 与 TtsMini 共用（同一单例、同一持久化逻辑）。Shared voice picker: used by both TtsSettings and TtsMini (same singleton, same persistence). -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { UiSelect } from '../ui'
import { ttsSettings, saveTts, getVoices, loadVoices, API_VOICE_SUGGESTIONS } from '../../composables/assistant/useTts'
import { useTtsEngine } from '../../composables/assistant/useTtsEngine'
import { useConfig } from '../../composables/useApi'

/** 组件 Props：标签。Component props: label. */
withDefaults(defineProps<{
  label?: string
}>(), { label: '角色' })

/** 引擎选择单例。Engine choice singleton. */
const { engine } = useTtsEngine()

/** 全局配置。Global config. */
const app = useConfig()

/** 浏览器可用语音列表。Available browser speech voices. */
const voices = ref<SpeechSynthesisVoice[]>([])

/** 是否 voiceclone 模型。Whether the model is voiceclone. */
const isVoiceClone = computed(() =>
  (app.config.value?.tts_model || '').toLowerCase().includes('voiceclone')
)

/**
 * API 音色候选：后端默认 voice + 预置音色；
 * 当前值是历史自定义名时插到最前，保证可见、可回选（下拉形态不再支持自由输入，
 * 自定义音色的编辑入口在卡2「音色」字段——那是后端 profile 配置）。
 *
 * API voice candidates: backend default + presets; a historical custom value is
 * prepended so it stays visible/selectable (the dropdown form drops free typing —
 * custom voices are edited in card 2's "voice" field, the backend profile config).
 */
const voiceOptions = computed(() => {
  const cfg = app.config.value?.tts_voice
  const list = [...API_VOICE_SUGGESTIONS]
  if (cfg && !list.includes(cfg)) list.unshift(cfg)
  const cur = ttsSettings.value.apiVoice
  if (cur && !list.includes(cur)) return [cur, ...list]
  return list
})

/** 挂载时加载浏览器语音列表。Load browser voices on mount. */
onMounted(() => {
  loadVoices(() => { voices.value = getVoices() })
})
</script>

<style scoped>
.voice-select { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
/* 标签：API 引擎时带后缀徽标。Label: suffixed with a badge on the API engine. */
.vs-label {
  font-size: var(--fs-2xs); color: var(--text-3);
  display: flex; justify-content: space-between; align-items: baseline;
}
.vs-label em {
  font-style: normal; font-family: var(--font-mono);
  color: var(--brand-c2); font-size: 10px;
}

/* voiceclone 说明。Voiceclone note. */
.vs-clone {
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.5; margin: 0;
  background: rgba(103, 232, 249, .06);
  border: 1px dashed rgba(103, 232, 249, .25);
  border-radius: var(--r-sm); padding: 6px 8px;
}
</style>
