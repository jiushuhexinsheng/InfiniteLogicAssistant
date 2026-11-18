<template>
  <!-- 识别：VAD / KWS / ASR —— 各自模式、模型下拉与推理参数。
       Recognition: VAD / KWS / ASR — per-capability mode, model picker and inference params. -->
  <h3 class="cs-title">VAD · 本地分段</h3>
  <SourceModeSwitch
    :model-value="s.ed().vad.mode"
    :options="[{ value: 'local', label: '本地', en: 'Local' }, { value: 'off', label: '关闭', en: 'Off' }]"
    label-zh="VAD 模式" label-en="VAD Mode"
    @update:model-value="v => (s.ed().vad.mode = v)"
  />
  <p v-if="s.ed().vad.mode === 'off'" class="cs-warn">
    VAD 已关闭：流式语音将无法启动（本地/云端 ASR 都需要 VAD 分段）。
  </p>
  <ModelConfigCard
    kind="vad" title-zh="本地 VAD 模型" title-en="Local VAD (sherpa-onnx)"
    :model-value="s.ed().vad.model"
    :model-options="modelOptions('vad')"
    :values="s.ed().vad"
    :params="schemaFor('vad')"
    :missing-hint="missingHint('vad', s.ed().vad.model)"
    placeholder="选择 VAD 模型 / Select VAD model"
    @update:model="v => switchModel('vad', v)"
  />

  <!-- ── KWS ── -->
  <h3 class="cs-title">KWS · 唤醒词</h3>
  <SourceModeSwitch
    :model-value="s.ed().kws.mode"
    :options="[
      { value: 'local', label: '本地', en: 'Local' },
      { value: 'api', label: '转写后判定', en: 'After ASR' },
      { value: 'off', label: '关闭', en: 'Off' },
    ]"
    label-zh="KWS 模式" label-en="KWS Mode"
    @update:model-value="v => (s.ed().kws.mode = v)"
  />
  <p class="cs-note">当前唤醒词：<strong>{{ currentWakeWords }}</strong></p>
  <SettingsButton
    class="kws-wake-link" zh="去唤醒页修改唤醒词" en="Edit wake words"
    @click="$emit('navigate', 'wake')"
  />
  <ModelConfigCard
    v-if="s.ed().kws.mode !== 'off'"
    kind="kws" title-zh="本地 KWS 模型" title-en="Local KWS (sherpa-onnx)"
    :model-value="s.ed().kws.model_dir"
    :model-options="modelOptions('kws')"
    :values="s.ed().kws"
    :params="schemaFor('kws')"
    :missing-hint="missingHint('kws', s.ed().kws.model_dir)"
    placeholder="选择 KWS 模型 / Select KWS model"
    @update:model="v => switchModel('kws', v)"
  />

  <!-- ── ASR ── -->
  <h3 class="cs-title">ASR · 语音识别</h3>
  <SourceModeSwitch
    :model-value="s.ed().asr.mode"
    :options="[
      { value: 'local', label: '本地', en: 'Local' },
      { value: 'cloud', label: 'API', en: 'API' },
      { value: 'hybrid', label: '混合', en: 'Hybrid' },
    ]"
    label-zh="ASR 模式" label-en="ASR Mode"
    @update:model-value="v => (s.ed().asr.mode = v)"
  />
  <p class="cs-hint">本地 / 混合模式边说边出字（流式）；云端模式在段落结束后整段出字。</p>
  <ModelConfigCard
    v-if="s.ed().asr.mode !== 'cloud'"
    kind="asr" title-zh="本地 ASR 模型" title-en="Local ASR (sherpa-onnx)"
    :model-value="s.ed().asr.local_model"
    :model-options="modelOptions('asr')"
    :values="s.ed().asr"
    :params="schemaFor('asr')"
    :missing-hint="missingHint('asr', s.ed().asr.local_model)"
    placeholder="选择 ASR 模型 / Select ASR model"
    @update:model="v => switchModel('asr', v)"
  />
</template>

<script setup lang="ts">
/**
 * 识别引擎段（VAD / KWS / ASR），从 LocalModelsCard 拆出。
 * Recognition section (VAD / KWS / ASR), extracted from LocalModelsCard.
 */
import ModelConfigCard from './ModelConfigCard.vue'
import SourceModeSwitch from './SourceModeSwitch.vue'
import SettingsButton from './SettingsButton.vue'
import { useSettings } from './useSettings'
import { useLocalModels } from './useLocalModels'

defineEmits<{ navigate: [tab: 'wake'] }>()

const s = useSettings()
const { currentWakeWords, modelOptions, missingHint, schemaFor, switchModel } = useLocalModels()
</script>

<style scoped>
.cs-title {
  margin: var(--sp-3) 0 var(--sp-1);
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  padding-top: var(--sp-2); border-top: var(--divider-dashed);
}
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 0; }
.cs-hint { font-size: var(--fs-2xs); color: var(--text-3); margin: var(--sp-q6) 0 0; line-height: 1.5; }
.cs-warn { margin: var(--sp-q6) 0 0; font-size: var(--fs-2xs); color: #fbbf24; line-height: 1.6; }
</style>
