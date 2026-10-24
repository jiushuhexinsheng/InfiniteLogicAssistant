<template>
  <!-- 卡2 内容：生效徽章 + 音色覆盖 + 音量（播放偏好，即时存本机）。
       语速/音调不在播放偏好：后端 /api/tts 只接受 text + voice；语速走合成卡本地 Kokoro 的 speed。
       Card 2 content: effective badges + voice override + volume (playback prefs, instant
       localStorage save). No rate/pitch: the backend /api/tts accepts only text + voice;
       speed lives in the local Kokoro card. -->
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

<script setup lang="ts">
import { computed } from 'vue'
import { UiRange } from '../ui'
import VoiceSelect from './VoiceSelect.vue'
import { ttsSettings, saveTts } from '../../composables/assistant/useTts'
import { useConfig } from '../../composables/useApi'

/** 获取应用配置。Get app config. */
const app = useConfig()

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
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.5; margin: 0;
}

/* 只读徽章行：当前 Profile / 模型。Read-only badges: active profile / model. */
.tts-badges { display: flex; gap: var(--sp-q6); flex-wrap: wrap; }
.tts-badge {
  display: inline-flex; align-items: center; gap: var(--sp-q6);
  font-size: var(--fs-2xs); font-family: var(--font-mono);
  color: var(--text-2);
  background: rgba(15, 23, 42, .6);
  border: 1px solid var(--border-soft);
  border-radius: var(--r-full);
  padding: var(--sp-1) var(--sp-q10);
  max-width: 100%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tts-badge em { font-style: normal; color: var(--text-3); }
</style>
