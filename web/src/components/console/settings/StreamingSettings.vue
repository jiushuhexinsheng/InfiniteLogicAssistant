<template>
  <!-- 流式会话参数：帧间隔 / 端点静音 / 最长语音。
       Streaming session params: partial interval / endpoint silence / max utterance. -->
  <h3 class="cs-title">流式会话</h3>
  <SettingsField label="启用 WebSocket 流式链路" en="Enable WebSocket streaming" row>
    <UiToggle :model-value="s.ed().streaming.enabled"
      @update:model-value="v => (s.ed().streaming.enabled = v)" />
  </SettingsField>
  <div class="cs-grid">
    <SettingsField label="partial 间隔（ms）" en="Partial interval (ms)">
      <UiInput type="number" min="30" :model-value="s.ed().streaming.partial_interval_ms"
        @update:model-value="v => (s.ed().streaming.partial_interval_ms = toNum(v))" />
    </SettingsField>
    <SettingsField label="端点静音（ms）" en="Endpoint silence (ms)">
      <UiInput type="number" min="100" :model-value="s.ed().streaming.endpoint_silence_ms"
        @update:model-value="v => (s.ed().streaming.endpoint_silence_ms = toNum(v))" />
    </SettingsField>
    <SettingsField label="最长语音（ms）" en="Max utterance (ms)">
      <UiInput type="number" min="1000" :model-value="s.ed().streaming.max_utterance_ms"
        @update:model-value="v => (s.ed().streaming.max_utterance_ms = toNum(v))" />
    </SettingsField>
  </div>
  <p class="cs-note">关闭后音频不再走流式链路；新链路不保留旧的浏览器切段上传回退。</p>
</template>

<script setup lang="ts">
/**
 * 流式会话段，从 LocalModelsCard 拆出。
 * Streaming session section, extracted from LocalModelsCard.
 */
import SettingsField from './SettingsField.vue'
import { UiInput, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { toNum } from './useLocalModels'

const s = useSettings()
</script>

<style scoped>
.cs-title {
  margin: var(--sp-3) 0 var(--sp-1);
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  padding-top: var(--sp-2); border-top: var(--divider-dashed);
}
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 0; }
.cs-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-2); }
</style>
