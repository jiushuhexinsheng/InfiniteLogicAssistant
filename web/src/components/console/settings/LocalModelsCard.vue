<template>
  <!-- 本地模型 / 硬件卡：外壳只负责标题、操作区与段落调度；各段落由独立 SFC 渲染。
       Local models / hardware card: the shell owns title, actions and section dispatch;
       each section is its own SFC. -->
  <SettingsCard :title="title" :title-en="titleEn">
    <template #actions>
      <template v-if="show('recognition') || show('tts')">
        <UiButton variant="secondary" size="sm" class="use-local" :disabled="loading" @click="oneClickLocal(scope)">
          <BiLabel :zh="useLocalLabel.zh" :en="useLocalLabel.en" layout="stack" />
        </UiButton>
        <UiButton variant="ghost" size="sm" :disabled="loading" @click="refresh">
          <BiLabel :zh="loading ? T.scanning.zh : T.refreshModels.zh"
                   :en="loading ? T.scanning.en : T.refreshModels.en" layout="stack" />
        </UiButton>
      </template>
      <UiButton v-if="!hideSave" variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="save">
        <BiLabel :zh="s.saving.value ? T.saving.zh : T.save.zh"
                 :en="s.saving.value ? T.saving.en : T.save.en" layout="stack" />
      </UiButton>
    </template>

    <template v-if="s.editable.value">
      <template v-if="show('overview') || show('recognition') || show('tts')">
        <p class="cs-note">
          模型目录：<code>models/{vad,kws,asr,tts,llm}</code>。把任意兼容 sherpa-onnx 的模型放进对应目录，
          点「刷新模型」即可选择；大模型可用
          <code>python scripts/fetch_models.py</code> 下载。
        </p>
        <p class="cs-note">
          推理硬件按能力独立选择 —— VAD 跑 CPU、ASR 跑 GPU 是允许的。
          当前可用 provider：<strong>{{ providers.join(' / ') || 'cpu' }}</strong>
          <span v-if="hw">（sherpa-onnx {{ hw.sherpa_version }}，{{ hw.cpu_count }} 核）</span>。
        </p>
      </template>

      <!-- 四能力状态 + 引擎自检。Status chips + engine self-tests. -->
      <LocalModelsStatus :scope="scope" />

      <!-- 各段落按 Tab 渲染。Sections render per tab. -->
      <RecognitionEngines v-if="show('recognition')" @navigate="$emit('navigate', $event)" />
      <LocalTtsModel v-if="show('tts')" />
      <StreamingSettings v-if="show('advanced')" />
      <HardwareSettings v-if="show('hardware')" />
    </template>
  </SettingsCard>
</template>

<script setup lang="ts">
/**
 * 本地模型与硬件卡外壳：按 Tab 调度识别 / 合成 / 流式 / 硬件段落。
 *
 * 拆分前本组件 610 行，混合了模型扫描、schema、自检、设备与四段模板；现在状态与
 * 动作在 `useLocalModels`，段落各自成组件，外壳只剩标题、操作区与调度。
 *
 * Shell for the local-models and hardware card: dispatches recognition / TTS /
 * streaming / hardware sections per tab. Before the split this component was 610 lines
 * mixing scanning, schemas, self-tests, devices and four template blocks; state and
 * actions now live in `useLocalModels`, sections are their own components, and the shell
 * keeps only the title, actions and dispatch.
 */
import { computed, onMounted } from 'vue'

import SettingsCard from './SettingsCard.vue'
import BiLabel from './BiLabel.vue'
import LocalModelsStatus from './LocalModelsStatus.vue'
import RecognitionEngines from './RecognitionEngines.vue'
import LocalTtsModel from './LocalTtsModel.vue'
import StreamingSettings from './StreamingSettings.vue'
import HardwareSettings from './HardwareSettings.vue'
import { UiButton } from '../../ui'
import { settingsText as T } from '../../../locales/settings'
import { useSettings } from './useSettings'
import { useLocalModels, type LocalModelsScope } from './useLocalModels'

const props = withDefaults(defineProps<{
  scope?: LocalModelsScope
  hideSave?: boolean
}>(), { scope: 'all', hideSave: false })

defineEmits<{ navigate: [tab: 'wake'] }>()

const s = useSettings()
const { providers, hw, loading, oneClickLocal, refresh } = useLocalModels()
const scope = computed(() => props.scope)

/** 当前段落是否渲染。Whether a section renders in this scope. */
function show(section: string): boolean {
  return props.scope === 'all' || props.scope === section
}

/** 一键本地按钮文案（识别页不碰 TTS）。One-click label per scope. */
const useLocalLabel = computed(() => {
  if (props.scope === 'recognition') return { zh: '一键本地识别', en: 'Use local recognition' }
  if (props.scope === 'tts') return { zh: '一键本地 TTS', en: 'Use local TTS' }
  return { zh: T.useLocal.zh, en: T.useLocal.en }
})

/** 卡片标题随 Tab 变化（中英）。Card title follows the tab (zh/en). */
const title = computed(() => {
  switch (props.scope) {
    case 'overview': return '语音总览'
    case 'recognition': return '识别引擎（VAD / KWS / ASR）'
    case 'tts': return '本地 TTS（Kokoro）'
    case 'hardware': return '麦克风与扬声器'
    case 'advanced': return '流式与高级'
    default: return '本地模型与硬件（sherpa-onnx）'
  }
})
const titleEn = computed(() => {
  switch (props.scope) {
    case 'overview': return 'Voice Overview'
    case 'recognition': return 'Recognition Engine'
    case 'tts': return 'Local TTS'
    case 'hardware': return 'Microphone & Speaker'
    case 'advanced': return 'Streaming & Advanced'
    default: return 'Local Models & Hardware'
  }
})

/** 保存本卡负责的模型配置。Save the model configuration owned by this card. */
function save() {
  void s.saveModule('models')
}

// 挂载即扫描模型/硬件（与拆分前一致）。Scan models/hardware on mount (unchanged).
onMounted(refresh)
</script>

<style scoped>
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 0; }
.cs-note code { font-family: var(--font-mono); }
</style>
