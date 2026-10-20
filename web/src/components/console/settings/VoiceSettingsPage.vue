<template>
  <!-- 语音设置统一入口：六个 Tab，避免 ASR/TTS/唤醒/模型四套菜单互相重复。
       Single voice entry with six tabs: avoids four overlapping menu pages. -->
  <div class="voice-settings">
    <div class="vs-tabs" role="tablist" aria-label="语音设置">
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        role="tab"
        class="vs-tab"
        :class="{ on: tab === t.id }"
        :aria-selected="tab === t.id"
        @click="tab = t.id"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="vs-body">
      <LocalModelsCard v-if="tab === 'overview'" scope="overview" />

      <VoiceCard v-else-if="tab === 'wake'" />

      <template v-else-if="tab === 'recognition'">
        <LocalModelsCard scope="recognition" />
        <ServiceCard :section="asrDef" />
      </template>

      <template v-else-if="tab === 'synthesis'">
        <TtsEngineCard />
        <ServiceCard v-if="engine === 'api'" :section="ttsDef">
          <TtsSettings />
        </ServiceCard>
        <LocalModelsCard v-else-if="engine === 'local'" scope="tts" />
        <TtsLocalCard v-else />
      </template>

      <LocalModelsCard v-else-if="tab === 'hardware'" scope="hardware" />
      <LocalModelsCard v-else-if="tab === 'advanced'" scope="advanced" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 语音设置页：把原「语音识别 / 语音合成 / 语音唤醒 / 本地模型」四页收口为
 * 概览 / 唤醒 / 识别 / 合成 / 硬件 / 高级 六个 Tab。
 *
 * Voice settings page: the former four menu entries collapse into six tabs.
 */
import { ref } from 'vue'
import LocalModelsCard from './LocalModelsCard.vue'
import VoiceCard from './VoiceCard.vue'
import TtsEngineCard from './TtsEngineCard.vue'
import TtsLocalCard from './TtsLocalCard.vue'
import TtsSettings from '../../assistant/TtsSettings.vue'
import ServiceCard from './ServiceCard.vue'
import { useTtsEngine } from '../../../composables/assistant/useTtsEngine'
import { sectionDefs } from './configDefs'

type TabId = 'overview' | 'wake' | 'recognition' | 'synthesis' | 'hardware' | 'advanced'
interface TabDef { id: TabId; label: string }

const tabs: TabDef[] = [
  { id: 'overview', label: '概览' },
  { id: 'wake', label: '唤醒' },
  { id: 'recognition', label: '识别' },
  { id: 'synthesis', label: '合成' },
  { id: 'hardware', label: '硬件' },
  { id: 'advanced', label: '高级' },
]

const tab = ref<TabId>('overview')
const { engine } = useTtsEngine()
const asrDef = sectionDefs.find(d => d.key === 'asr')!
const ttsDef = sectionDefs.find(d => d.key === 'tts')!
</script>

<style scoped>
.voice-settings {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.vs-tabs {
  display: flex;
  gap: var(--sp-q6);
  padding: var(--sp-q6);
  border: 1px solid var(--border-soft);
  border-radius: var(--r-md);
  background: rgba(15, 23, 42, .55);
  overflow-x: auto;
  flex-shrink: 0;
}
.vs-tab {
  flex: none;
  padding: var(--sp-q6) var(--sp-3);
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-3);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast);
}
.vs-tab:hover { color: var(--text-1); background: rgba(148, 163, 184, .08); }
.vs-tab.on {
  color: var(--text-1);
  background: var(--brand-grad);
  border-color: transparent;
}
.vs-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-q14);
  overflow: hidden;
}
</style>
