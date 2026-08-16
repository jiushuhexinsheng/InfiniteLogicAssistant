<template>
  <div class="console-settings">
    <div class="cs-head">
      <h2 class="cs-title"><Icon name="settings" :size="17" /> 设置</h2>
      <p class="cs-sub">语音播报设置 —— 调节音量 / 语速 / 声音，改动自动保存</p>
    </div>

    <div class="cs-card">
      <TtsSettings />
    </div>

    <p class="cs-note">
      API 语音需在 config.yaml 的 voice.tts 配置 endpoint / api_key / model；voiceclone 模型的声音来自 voice_ref 参考音频。
    </p>
  </div>
</template>

<script setup lang="ts">
import Icon from '../Icon.vue'
import TtsSettings from '../assistant/TtsSettings.vue'
</script>

<style scoped>
.console-settings {
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cs-head { display: flex; flex-direction: column; gap: 4px; }
.cs-title {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: var(--fs-lg); font-weight: 700; letter-spacing: .03em;
  color: var(--text-1); margin: 0;
}
.cs-title :deep(svg) { color: var(--brand-c2); }
.cs-sub { font-size: var(--fs-xs); color: var(--text-3); margin: 0; }

.cs-card { max-width: 560px; }
.cs-note {
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6;
  max-width: 560px; margin: 0;
}
</style>
