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
        <span v-if="tabDot(t.id)" class="vs-dot" :class="tabDot(t.id)"></span>
        <span class="vs-tab-zh">{{ t.labelZh }}</span>
        <span class="vs-tab-en">{{ t.labelEn }}</span>
      </button>
    </div>

    <div class="vs-body">
      <VoiceOverview v-if="tab === 'overview'" @select="onChainSelect" />

      <VoiceCard v-else-if="tab === 'wake'" @navigate="tab = $event" />

      <template v-else-if="tab === 'recognition'">
        <div class="vs-actions">
          <SettingsButton
            class="vs-save-recognition" variant="primary"
            :loading="settings.saving.value"
            :zh="settings.saving.value ? '保存中…' : '保存识别配置'"
            :en="settings.saving.value ? 'Saving…' : 'Save recognition'"
            @click="saveRecognition"
          />
        </div>
        <LocalModelsCard scope="recognition" hide-save />
        <UiDisclosure v-model="cloudOpen" class="vs-cloud">
          <template #head>
            <span class="vs-cloud-head">云端 ASR 配置 <i>Cloud ASR</i> · 仅 cloud / hybrid 使用</span>
          </template>
          <template #collapsed>
            <span class="vs-cloud-hint">供应商 / API Key / 云端模型 ID（当前折叠）</span>
          </template>
          <ModelProviderPanel section="asr" :compact="false" />
          <ServiceCard :section="asrDef" hide-save />
        </UiDisclosure>
      </template>

      <template v-else-if="tab === 'synthesis'">
        <TtsEngineCard />
        <ModelProviderPanel v-if="engine === 'api'" section="tts" />
        <ServiceCard v-if="engine === 'api'" :section="ttsDef">
          <TtsSettings />
        </ServiceCard>
        <LocalModelsCard v-else scope="tts" />
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
import { computed, onMounted, ref, watch } from 'vue'
import LocalModelsCard from './LocalModelsCard.vue'
import ModelProviderPanel from './ModelProviderPanel.vue'
import VoiceOverview from './VoiceOverview.vue'
import VoiceCard from './VoiceCard.vue'
import TtsEngineCard from './TtsEngineCard.vue'
import SettingsButton from './SettingsButton.vue'
import TtsSettings from '../../assistant/TtsSettings.vue'
import ServiceCard from './ServiceCard.vue'
import { useTtsEngine } from '../../../composables/assistant/useTtsEngine'
import { sectionDefs } from './configDefs'
import { UiDisclosure } from '../../ui'
import { settingsText as T } from '../../../locales/settings'
import { useVoiceModuleStatus } from '../../../composables/useVoiceModuleStatus'
import { useSettings } from './useSettings'

type TabId = 'overview' | 'wake' | 'recognition' | 'synthesis' | 'hardware' | 'advanced'
interface TabDef { id: TabId; labelZh: string; labelEn: string }

const tabs: TabDef[] = [
  { id: 'overview', labelZh: T.overview.zh, labelEn: T.overview.en },
  { id: 'wake', labelZh: T.wake.zh, labelEn: T.wake.en },
  { id: 'recognition', labelZh: T.recognition.zh, labelEn: T.recognition.en },
  { id: 'synthesis', labelZh: T.synthesis.zh, labelEn: T.synthesis.en },
  { id: 'hardware', labelZh: T.hardware.zh, labelEn: T.hardware.en },
  { id: 'advanced', labelZh: T.advanced.zh, labelEn: T.advanced.en },
]

const tab = ref<TabId>('overview')
const settings = useSettings()
/** 云端 ASR 配置是否展开：本地模式默认折叠。Whether the cloud ASR block is open. */
const cloudOpen = ref(true)
watch(() => settings.sec('asr')?.mode, (mode) => {
  if (mode) cloudOpen.value = mode !== 'local'
}, { immediate: true })

/** 识别 Tab 统一保存：本地引擎 + 云端 profile 一次 PATCH。Unified recognition save. */
function saveRecognition(): void {
  void settings.saveModule('recognition')
}
const { engine } = useTtsEngine()
const { status, refreshVoiceStatus } = useVoiceModuleStatus()

/** 链路节点点击：语音节点跳 Tab，LLM 节点跳左侧「大模型」菜单。
 *  Chain-node click: voice nodes jump a tab, the LLM node jumps to the 大模型 menu. */
function onChainSelect(target: 'recognition' | 'synthesis' | 'llm') {
  if (target === 'llm') settings.activeMenu.value = 'llm'
  else tab.value = target
}
const asrDef = sectionDefs.find(d => d.key === 'asr')!
const ttsDef = sectionDefs.find(d => d.key === 'tts')!

/** Tab 上的小状态灯（没有状态概念的 Tab 不显示）。Tab status dots. */
const tabDot = computed(() => (id: TabId): '' | 'ok' | 'err' => {
  if (!status.value) return ''
  if (id === 'wake') return status.value.kws.ready ? 'ok' : 'err'
  if (id === 'recognition') {
    const s = status.value
    return s.vad.ready && s.kws.ready && s.asr.ready ? 'ok' : 'err'
  }
  if (id === 'synthesis') return status.value.tts.ready ? 'ok' : 'err'
  return ''
})

onMounted(() => { void refreshVoiceStatus() })
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
  display: inline-flex; align-items: baseline; gap: var(--sp-q6);
  padding: var(--sp-q6) var(--sp-3);
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-3);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast);
}
.vs-tab-zh { font-size: var(--fs-xs); }
.vs-tab-en { font-size: var(--fs-2xs); opacity: .7; }
.vs-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); }
.vs-dot.ok { background: #34d399; box-shadow: 0 0 5px rgba(52, 211, 153, .6); }
.vs-dot.err { background: #f87171; }
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
  /* 一个 Tab 可能有多张卡（识别 = 本地引擎 + 供应商 + API Profile）。整页滚动，
     卡片保持自然高度；否则 flex 收缩会把后面的卡片卡头和卡体压没。
     A tab can hold several cards (recognition = local engines + providers + API
     profile). Scroll the page and keep cards at natural height; otherwise flex
     shrinking collapses later cards' bodies. */
  overflow-y: auto;
}
.vs-body :deep(.cs-card) {
  flex: 0 0 auto;
}
.vs-body :deep(.cs-card-body) {
  overflow: visible;
}
</style>


<style scoped>
.vs-actions { display: flex; justify-content: flex-end; }
.vs-cloud-head { font-size: var(--fs-2xs); color: var(--text-2); }
.vs-cloud-head i { font-style: normal; color: var(--text-3); }
.vs-cloud-hint { font-size: var(--fs-2xs); color: var(--text-3); }
</style>
