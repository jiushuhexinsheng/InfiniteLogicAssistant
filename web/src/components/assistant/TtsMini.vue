<template>
  <!-- TTS 迷你控制面板：语音唤醒和播报的快捷开关。TTS mini control panel: quick toggles for voice wake and speech. -->
  <div class="tts-mini">
    <div class="tm-row">
      <div class="tm-left">
        <b>语音唤醒 &amp; 播报</b>
        <span>浏览器 SpeechSynthesis · 后端 TTS 可选</span>
      </div>
      <!-- 开关组。Toggle group. -->
      <div class="tm-toggles">
        <div class="tm-toggle">
          <!-- 语音唤醒开关。Voice wake toggle. -->
          <UiToggle :model-value="wakeEnabled" @update:model-value="toggleWake()" />
          <span>唤醒</span>
        </div>
        <div class="tm-toggle">
          <!-- 语音播报开关。Speech playback toggle. -->
          <UiToggle :model-value="speakEnabled" @update:model-value="toggleSpeak()" />
          <span>播报</span>
        </div>
      </div>
    </div>
    <!-- 更多设置入口链接。More settings entry link. -->
    <RouterLink class="tm-more" to="/console">更多设置 → 控制台</RouterLink>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAssistant } from '../../composables/useAssistant'
import { ttsSettings, toggleSpeak } from '../../composables/assistant/useTts'
import { UiToggle } from '../ui'

/** 获取助手实例。Get assistant instance. */
const asst = useAssistant()

/**
 * 计算语音唤醒是否启用。Compute whether voice wake is enabled.
 */
const wakeEnabled = computed(() => asst.wakeEnabled.value)

/**
 * 计算语音播报是否启用。Compute whether speech playback is enabled.
 */
const speakEnabled = computed(() => ttsSettings.value.speakEnabled)

/**
 * 切换语音唤醒状态。Toggle voice wake state.
 */
function toggleWake() {
  void asst.toggleWake()
}
</script>

<style scoped>
/* TTS 迷你面板容器。TTS mini panel container. */
.tts-mini { display: flex; flex-direction: column; gap: 10px; }
/* 行布局。Row layout. */
.tm-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
/* 左侧信息区。Left info area. */
.tm-left { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.tm-left b { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); white-space: nowrap; }
.tm-left span { font-size: var(--fs-2xs); color: var(--text-3); }
/* 开关组。Toggle group. */
.tm-toggles { display: flex; gap: 14px; flex-shrink: 0; }
/* 单个开关项。Single toggle item. */
.tm-toggle { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.tm-toggle span { font-size: var(--fs-2xs); color: var(--text-3); }
/* 更多设置链接。More settings link. */
.tm-more {
  align-self: flex-end; font-size: var(--fs-2xs); color: var(--brand-c2);
  text-decoration: none; letter-spacing: .02em;
  transition: color var(--dur-fast);
}
.tm-more:hover { color: var(--brand-c1); }
</style>
