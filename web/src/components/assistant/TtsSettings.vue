<template>
  <!-- TTS 设置面板：语音引擎切换、声音选择、音量/语速/音调调节。TTS settings panel: engine switch, voice selection, volume/rate/pitch controls. -->
  <div class="tts-settings">
    <!-- 标题栏 + 试听按钮。Header + test button. -->
    <div class="tts-head">
      <span class="tts-title"><Icon name="volume" :size="13" /> 语音设置</span>
      <button class="tts-test" @click="testVoice()"><Icon name="play" :size="10" /> 试听</button>
    </div>

    <!-- 引擎切换：本地语音（浏览器 SpeechSynthesis）/ API 语音（后端 TTS）。Engine switch: local (browser SpeechSynthesis) / API (backend TTS). -->
    <div class="tts-engine">
      <button class="eng-btn" :class="{ on: engine === 'browser' }" @click="setEngine('browser')">本地语音</button>
      <button
        class="eng-btn"
        :class="{ on: engine === 'api', disabled: !apiAvailable }"
        :disabled="!apiAvailable"
        :title="apiAvailable ? '' : '未配置 TTS API'"
        @click="setEngine('api')"
      >API 语音</button>
    </div>
    <!-- API 不可用时的提示。Hint when API is unavailable. -->
    <p v-if="!apiAvailable" class="tts-hint">API 语音需在 config.yaml 的 voice.tts 配好 endpoint / api_key 后启用</p>

    <!-- 声音选择：浏览器=系统语音下拉；API=名字输入（可下拉/自定义）。
         Voice selection: browser = system voice dropdown; API = name input (with datalist/custom). -->
    <label v-if="engine === 'browser'" class="tts-field">
      <span class="tts-label">声音</span>
      <select v-model="ttsSettings.voiceName" @change="saveTts()">
        <option value="">系统默认</option>
        <option v-for="v in voices" :key="v.name" :value="v.name">{{ v.name }}</option>
      </select>
    </label>
    <label v-else class="tts-field">
      <span class="tts-label">声音 <em>API</em></span>
      <!-- voiceclone 模型：声音由后端 voice_ref 参考音频决定，无需前端选。
           Voiceclone model: voice determined by backend voice_ref audio, no frontend selection needed. -->
      <p v-if="isVoiceClone" class="tts-voiceclone-note">克隆 voice_ref 参考音频（在 config.yaml 的 voice.tts 配置）</p>
      <template v-else>
        <input
          class="tts-voice-input"
          list="tts-voices"
          v-model="ttsSettings.apiVoice"
          placeholder="选一个或自定义"
          @change="saveTts()"
          @blur="saveTts()"
        />
        <datalist id="tts-voices">
          <option v-for="s in apiVoiceOptions" :key="s" :value="s">{{ s }}</option>
        </datalist>
      </template>
    </label>

    <!-- 音量滑块（两引擎通用）。Volume slider (shared by both engines). -->
    <label class="tts-field">
      <span class="tts-label">音量 <em>{{ pct(ttsSettings.volume) }}</em></span>
      <input type="range" min="0" max="1" step="0.05" v-model.number="ttsSettings.volume" @change="saveTts()" />
    </label>

    <!-- 语速 / 音调（仅本地语音引擎生效）。Rate / Pitch (only effective for local engine). -->
    <template v-if="engine === 'browser'">
      <label class="tts-field">
        <span class="tts-label">语速 <em>{{ ttsSettings.rate.toFixed(1) }}×</em></span>
        <input type="range" min="0.5" max="2" step="0.1" v-model.number="ttsSettings.rate" @change="saveTts()" />
      </label>
      <label class="tts-field">
        <span class="tts-label">音调 <em>{{ ttsSettings.pitch.toFixed(1) }}</em></span>
        <input type="range" min="0.5" max="1.5" step="0.1" v-model.number="ttsSettings.pitch" @change="saveTts()" />
      </label>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import Icon from '../Icon.vue'
import { ttsSettings, saveTts, getVoices, loadVoices, testVoice, API_VOICE_SUGGESTIONS } from '../../composables/assistant/useTts'
import type { TtsEngine } from '../../composables/assistant/useTts'
import { useConfig } from '../../composables/useApi'

/** 获取应用配置。Get app config. */
const app = useConfig()

/** 浏览器可用语音列表。Available browser speech voices. */
const voices = ref<SpeechSynthesisVoice[]>([])

/**
 * API 引擎可用性：后端 /api/config 的 tts_available 字段。
 * API engine availability: tts_available field from backend /api/config.
 */
const apiAvailable = computed(() => app.config.value?.tts_available === true)

/**
 * 是否为 voiceclone 模型：声音来自后端 voice_ref，前端不选名字。
 * Whether using voiceclone model: voice from backend voice_ref, no frontend name selection.
 */
const isVoiceClone = computed(() =>
  (app.config.value?.tts_model || '').toLowerCase().includes('voiceclone')
)

/**
 * 当前生效引擎：设置里选了 API 但后端未启用时，强制回退到浏览器引擎展示。
 * Current effective engine: fallback to browser if API is selected but backend not available.
 */
const engine = computed<TtsEngine>(() =>
  ttsSettings.value.engine === 'api' && apiAvailable.value ? 'api' : 'browser'
)

/**
 * API 声音建议列表：标准音色 + 后端配置的默认 voice。
 * API voice suggestions: standard voices + backend-configured default voice.
 */
const apiVoiceOptions = computed(() => {
  const cfg = app.config.value?.tts_voice
  const list = [...API_VOICE_SUGGESTIONS]
  if (cfg && !list.includes(cfg)) list.unshift(cfg)
  return list
})

/**
 * 设置 TTS 引擎（API 不可用时忽略）。Set TTS engine (ignored when API is unavailable).
 * @param e - 目标引擎。Target engine.
 */
function setEngine(e: TtsEngine) {
  if (e === 'api' && !apiAvailable.value) return
  ttsSettings.value.engine = e
  saveTts()
}

/**
 * 将 0~1 的数值转为百分比字符串。Convert 0~1 number to percentage string.
 * @param n - 数值（0~1）。Number (0~1).
 */
function pct(n: number) { return Math.round(n * 100) + '%' }

/** 组件挂载时加载浏览器语音列表。Load browser voices on mount. */
onMounted(() => {
  loadVoices(() => { voices.value = getVoices() })
})
</script>

<style scoped>
/* TTS 设置面板容器。TTS settings panel container. */
.tts-settings {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  background: var(--glass-bg-strong);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-2);
}
/* 标题栏。Header bar. */
.tts-head { display: flex; align-items: center; justify-content: space-between; }
.tts-title {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--fs-xs); font-weight: 600; color: var(--text-1);
}
/* 试听按钮。Test/preview button. */
.tts-test {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: var(--fs-2xs); font-family: var(--font-mono);
  color: var(--brand-c2); background: rgba(103, 232, 249, .08);
  border: 1px solid rgba(103, 232, 249, .25);
  padding: 3px 9px; border-radius: var(--r-full); cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast);
}
.tts-test:hover { background: rgba(103, 232, 249, .16); border-color: var(--brand-c2); }

/* 引擎切换按钮组。Engine switch button group. */
.tts-engine {
  display: flex; gap: 6px;
}
.eng-btn {
  flex: 1; font-size: var(--fs-2xs); font-family: var(--font-mono);
  color: var(--text-2); background: rgba(15, 23, 42, .6);
  border: 1px solid var(--border-soft); border-radius: var(--r-full);
  padding: 4px 8px; cursor: pointer;
  transition: color var(--dur-fast), border-color var(--dur-fast), background var(--dur-fast);
}
.eng-btn.on { color: var(--brand-c2); border-color: var(--brand-c2); background: rgba(103, 232, 249, .1); }
.eng-btn.disabled { opacity: .45; cursor: not-allowed; }

/* 提示文本。Hint text. */
.tts-hint { font-size: 10px; color: var(--text-3); line-height: 1.5; margin: 0; }
/* voiceclone 模型说明。Voiceclone model note. */
.tts-voiceclone-note {
  font-size: 10px; color: var(--text-3); line-height: 1.5; margin: 0;
  background: rgba(103, 232, 249, .06); border: 1px dashed rgba(103, 232, 249, .25);
  border-radius: var(--r-sm); padding: 6px 8px;
}

/* 设置字段。Settings field. */
.tts-field { display: flex; flex-direction: column; gap: 5px; }
/* 字段标签（左侧文字 + 右侧值）。Field label (left text + right value). */
.tts-label {
  font-size: var(--fs-2xs); color: var(--text-3);
  display: flex; justify-content: space-between; align-items: baseline;
}
.tts-label em { font-style: normal; font-family: var(--font-mono); color: var(--brand-c2); font-size: 10px; }

/* 下拉选择和输入框。Select dropdown and input. */
.tts-field select,
.tts-voice-input {
  background: rgba(15, 23, 42, .8); color: var(--text-1);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  font-size: var(--fs-xs); font-family: var(--font-mono);
  padding: 5px 8px; outline: none;
}
.tts-voice-input { width: 100%; }
.tts-field select:focus,
.tts-voice-input:focus { border-color: var(--brand-c2); }

/* 范围滑块。Range slider. */
.tts-field input[type="range"] {
  -webkit-appearance: none;
  appearance: none;
  width: 100%; height: 4px; border-radius: var(--r-full);
  background: linear-gradient(90deg, var(--brand-c1), var(--brand-c3));
  outline: none; cursor: pointer;
}
/* Webkit 滑块拇指。Webkit slider thumb. */
.tts-field input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 13px; height: 13px; border-radius: 50%;
  background: #fff; border: 2px solid var(--brand-c2);
  box-shadow: 0 0 6px rgba(103, 232, 249, .55);
  cursor: pointer;
}
/* Firefox 滑块拇指。Firefox slider thumb. */
.tts-field input[type="range"]::-moz-range-thumb {
  width: 13px; height: 13px; border-radius: 50%;
  background: #fff; border: 2px solid var(--brand-c2);
  cursor: pointer;
}
</style>
