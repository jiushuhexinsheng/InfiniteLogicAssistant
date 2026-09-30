<template>
  <!-- 按当前引擎渲染对应设置组（引擎选择与播报开关在卡1，本组件是卡2 的内容）。
       Renders the settings group for the current engine (engine picker and master
       switch live in card 1; this component is card 2's content). -->

  <!-- ── 本地：角色 / 音量 / 语速 / 音调（浏览器引擎） ──
       Local: voice / volume / rate / pitch (browser engine). -->
  <template v-if="engine === 'browser'">
    <VoiceSelect label="声音" />
    <UiRange
      label="音量"
      :model-value="ttsSettings.volume"
      :min="0"
      :max="1"
      :step="0.05"
      :value-text="pct(ttsSettings.volume)"
      @update:model-value="v => (ttsSettings.volume = v)"
      @change="saveTts()"
    />
    <UiRange
      label="语速"
      :model-value="ttsSettings.rate"
      :min="0.5"
      :max="2"
      :step="0.1"
      :value-text="ttsSettings.rate.toFixed(1) + '×'"
      @update:model-value="v => (ttsSettings.rate = v)"
      @change="saveTts()"
    />
    <UiRange
      label="音调"
      :model-value="ttsSettings.pitch"
      :min="0.5"
      :max="1.5"
      :step="0.1"
      :value-text="ttsSettings.pitch.toFixed(1)"
      @update:model-value="v => (ttsSettings.pitch = v)"
      @change="saveTts()"
    />
  </template>

  <!-- ── API：生效徽章 + 角色覆盖 + 音量（播放偏好，即时存本机）。
       语速/音调不在此组：后端 /api/tts 只接受 text + voice，无 rate/pitch 参数。
       API: effective badges + voice override + volume (playback prefs, instant
       localStorage save). No rate/pitch: the backend /api/tts accepts only text + voice. ── -->
  <template v-else>
    <div v-if="ttsProfile || ttsModel" class="tts-badges">
      <span v-if="ttsProfile" class="tts-badge"><em>Profile</em>{{ ttsProfile }}</span>
      <span v-if="ttsModel" class="tts-badge"><em>模型</em>{{ ttsModel }}</span>
    </div>
    <p class="tts-instant">♪ 播放偏好（音色 / 音量）即时保存到本机，不随上方「保存」提交后端配置。</p>
    <VoiceSelect label="音色" />
    <UiRange
      label="音量"
      :model-value="ttsSettings.volume"
      :min="0"
      :max="1"
      :step="0.05"
      :value-text="pct(ttsSettings.volume)"
      @update:model-value="v => (ttsSettings.volume = v)"
      @change="saveTts()"
    />
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { UiRange } from '../ui'
import VoiceSelect from './VoiceSelect.vue'
import { ttsSettings, saveTts } from '../../composables/assistant/useTts'
import { useTtsEngine } from '../../composables/assistant/useTtsEngine'
import { useConfig } from '../../composables/useApi'

/** 获取应用配置。Get app config. */
const app = useConfig()

/** 引擎选择（与卡1 同源）。Engine choice (same source as card 1). */
const { engine } = useTtsEngine()

/** 当前生效的后端 Profile 名（只读徽章）。Active backend profile name (read-only badge). */
const ttsProfile = computed(() => app.config.value?.tts_profile || '')

/** 当前生效的后端模型名（只读徽章）。Active backend model name (read-only badge). */
const ttsModel = computed(() => app.config.value?.tts_model || '')

/**
 * 将 0~1 的数值转为百分比字符串。Convert 0~1 number to percentage string.
 * @param n - 数值（0~1）。Number (0~1).
 */
function pct(n: number) { return Math.round(n * 100) + '%' }
</script>

<style scoped>
/* 即时保存说明。Instant-save note. */
.tts-instant {
  font-size: 10px; color: var(--text-3); line-height: 1.5; margin: 0;
}

/* 只读徽章行：当前 Profile / 模型。Read-only badges: active profile / model. */
.tts-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.tts-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 10px; font-family: var(--font-mono);
  color: var(--text-2);
  background: rgba(15, 23, 42, .6);
  border: 1px solid var(--border-soft);
  border-radius: var(--r-full);
  padding: 3px 9px;
  max-width: 100%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tts-badge em { font-style: normal; color: var(--text-3); }
</style>
