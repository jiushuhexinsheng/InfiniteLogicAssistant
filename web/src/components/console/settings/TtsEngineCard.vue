<template>
  <!-- 卡1：引擎选择（第一眼决定本地 / API），附播报总开关与试听。
       Card 1: engine choice (local vs API at first glance), plus the master switch and preview. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">语音引擎</span>
      <UiButton variant="ghost" size="sm" @click="testVoice()">
        <UiIcon name="play" :size="10" /> 试听
      </UiButton>
    </div>

    <!-- 大选择卡：本地（浏览器）/ API（后端）。Large picker cards: local (browser) / API (backend). -->
    <UiRadioCard
      :model-value="engine"
      :options="ENGINE_OPTIONS"
      aria-label="语音引擎"
      @update:model-value="v => setEngine(v as TtsEngine)"
    />
    <!-- 选了 API 但后端未启用：指路到下方配置卡（不回退引擎，否则永远到不了配置卡）。
         API chosen but backend off: point to the config card below (no engine fallback, or the config card would be unreachable). -->
    <p v-if="engine === 'api' && !apiAvailable" class="cs-hint">
      后端 TTS 未启用 —— 请在下方「TTS 语音合成」卡打开「启用」、配好 Profile / Endpoint / API Key 并保存；期间播报自动回退本地。
    </p>

    <!-- 播报总开关：关 = 回复仅文本不朗读（试听不受影响）。localStorage 即时生效，两引擎共用。
         Master switch: off = text-only replies (preview unaffected). Instant localStorage, shared by both engines. -->
    <div class="cs-row">
      <span class="cs-row-label">启用语音播报<em class="cs-row-sub">回复内容自动朗读；关闭后仅「试听」发声</em></span>
      <UiToggle
        :model-value="ttsSettings.speakEnabled"
        @update:model-value="toggleSpeak()"
        aria-label="启用语音播报"
      />
    </div>
  </UiCard>
</template>

<script setup lang="ts">
/**
 * 语音引擎选择卡（两卡堆叠的卡1）。
 * Engine-picker card (first of the two stacked cards).
 *
 * 引擎状态来自 useTtsEngine 单例（卡2 的配置卡与播报面板共用同一来源）。
 * Engine state comes from the useTtsEngine singleton (shared with card 2).
 */
import { UiButton, UiCard, UiIcon, UiRadioCard, UiToggle } from '../../ui'
import type { RadioCardOption } from '../../ui'
import { ttsSettings, testVoice, toggleSpeak } from '../../../composables/assistant/useTts'
import type { TtsEngine } from '../../../composables/assistant/useTts'
import { useTtsEngine } from '../../../composables/assistant/useTtsEngine'

/** 引擎选项（与 UiRadioCard 契约）。Engine options (UiRadioCard contract). */
const ENGINE_OPTIONS: RadioCardOption[] = [
  { value: 'browser', icon: 'wave', label: '本地语音', hint: '浏览器朗读 · 零配置' },
  { value: 'api', icon: 'bot', label: 'API 语音', hint: '后端合成 · 更自然' },
]

const { engine, apiAvailable, setEngine } = useTtsEngine()
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); letter-spacing: .02em; }

/* 引导提示。Guidance hint. */
.cs-hint {
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 0;
  background: rgba(251, 191, 36, .06);
  border: 1px dashed rgba(251, 191, 36, .3);
  border-radius: var(--r-sm); padding: 7px 9px;
}

/* 播报总开关行：左文右开关。Master-switch row: label left, toggle right. */
.cs-row {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 9px 11px;
  background: rgba(15, 23, 42, .6);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
}
.cs-row-label {
  display: flex; flex-direction: column; gap: 2px;
  font-size: var(--fs-xs); color: var(--text-2);
}
.cs-row-sub { font-style: normal; font-size: 10px; color: var(--text-3); line-height: 1.4; }
</style>
