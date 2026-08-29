<template>
  <div class="tts-mini">
    <div class="tm-row">
      <div class="tm-left">
        <b>语音唤醒 &amp; 播报</b>
        <span>浏览器 SpeechSynthesis · 后端 TTS 可选</span>
      </div>
      <div class="tm-toggles">
        <div class="tm-toggle">
          <UiToggle :model-value="wakeEnabled" @update:model-value="toggleWake()" />
          <span>唤醒</span>
        </div>
        <div class="tm-toggle">
          <UiToggle :model-value="speakEnabled" @update:model-value="toggleSpeak()" />
          <span>播报</span>
        </div>
      </div>
    </div>
    <RouterLink class="tm-more" to="/console">更多设置 → 控制台</RouterLink>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAssistant } from '../../composables/useAssistant'
import { ttsSettings, toggleSpeak } from '../../composables/assistant/useTts'
import { UiToggle } from '../ui'

const asst = useAssistant()
const wakeEnabled = computed(() => asst.wakeEnabled.value)
const speakEnabled = computed(() => ttsSettings.value.speakEnabled)

function toggleWake() {
  void asst.toggleWake()
}
</script>

<style scoped>
.tts-mini { display: flex; flex-direction: column; gap: 10px; }
.tm-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.tm-left { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.tm-left b { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); white-space: nowrap; }
.tm-left span { font-size: var(--fs-2xs); color: var(--text-3); }
.tm-toggles { display: flex; gap: 14px; flex-shrink: 0; }
.tm-toggle { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.tm-toggle span { font-size: var(--fs-2xs); color: var(--text-3); }
.tm-more {
  align-self: flex-end; font-size: var(--fs-2xs); color: var(--brand-c2);
  text-decoration: none; letter-spacing: .02em;
  transition: color var(--dur-fast);
}
.tm-more:hover { color: var(--brand-c1); }
</style>
