<template>
  <!-- 唤醒页：唤醒词 + 交互时序 + 交互行为 + 折叠的隐私边界。
       Wake page: wake words, interaction timing, behaviour, and a collapsible privacy note. -->
  <SettingsCard title="唤醒与交互" title-en="Wake & Interaction">
    <template #actions>
      <SettingsButton
        variant="primary" :loading="s.saving.value"
        :zh="s.saving.value ? '保存中…' : '保存'"
        :en="s.saving.value ? 'Saving…' : 'Save'"
        @click="saveVoice"
      />
    </template>

    <!-- 本地 KWS 状态：模式 / 模型 / 阈值一眼可见；灵敏度调整统一在识别页。 -->
    <div class="wk-status">
      <span class="wk-status-main">
        <UiStatusDot :color="kwsToneColor" :size="8" :glow="kwsReady ? 6 : 0" />
        <b>{{ kwsModeLabel }}</b>
        <span class="wk-status-detail" :title="kwsModelTitle">{{ kwsDetail }}</span>
      </span>
      <SettingsButton class="wk-adjust" zh="去识别调整" en="Adjust in Recognition"
                      @click="$emit('navigate', 'recognition')" />
    </div>

    <h3 class="wk-section">唤醒词 <i>Wake words</i></h3>
    <SettingsField v-if="s.editable.value" label="唤醒启用" en="Wake enabled" row>
      <UiToggle :model-value="s.ed().wake_word.enabled" @update:model-value="v => (s.ed().wake_word.enabled = v)" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="唤醒词（可多个，任一命中即唤醒）" en="Wake words">
      <div v-for="(_, i) in (s.ed().wake_word.keywords || [])" :key="i" class="wk-kwrow">
        <UiInput v-model="s.ed().wake_word.keywords[i]" placeholder="如 衍衡" />
        <SettingsButton
          variant="secondary" hover="danger" zh="删除" en="Delete"
          :disabled="(s.ed().wake_word.keywords || []).length <= 1"
          @click="s.ed().wake_word.keywords.splice(i, 1)"
        />
      </div>
      <SettingsButton variant="secondary" zh="新增唤醒词" en="Add wake word"
                      @click="s.ed().wake_word.keywords.push('')" />
      <p class="wk-hint">按发音判定：同音字（燕恒/言恒）同样命中；本地 KWS 的灵敏度在识别页调整。</p>
    </SettingsField>

    <h3 class="wk-section">交互时序 <i>Timing</i></h3>
    <div class="wk-grid">
      <SettingsField v-if="s.editable.value" label="唤醒后等指令窗（ms）" en="Command window (ms)">
        <UiInput type="number" min="1" :model-value="s.ed().vad.answer_timeout_ms"
                 @update:model-value="v => (s.ed().vad.answer_timeout_ms = toNum(v))" />
        <p class="wk-hint">只喊唤醒词、不带指令时等待多久。</p>
      </SettingsField>
      <SettingsField v-if="s.editable.value" label="续聊窗口（ms，0=关）" en="Follow-up window (ms)">
        <UiInput type="number" min="0" :model-value="s.ed().vad.followup_window_ms"
                 @update:model-value="v => (s.ed().vad.followup_window_ms = toNum(v))" />
        <p class="wk-hint">回合结束后免唤醒直接接话的时长。</p>
      </SettingsField>
      <SettingsField v-if="s.editable.value" label="聆听空闲超时（秒，0=永不）" en="Idle timeout (s)">
        <UiInput type="number" min="0" :model-value="s.ed().vad.listen_idle_s"
                 @update:model-value="v => (s.ed().vad.listen_idle_s = toNum(v))" />
        <p class="wk-hint">无实质信息多久后转入静待（麦克风保持监听）。</p>
      </SettingsField>
    </div>

    <h3 class="wk-section">交互行为 <i>Interaction</i></h3>
    <SettingsField v-if="s.editable.value" label="打断播报（助手说话时可直接开口）" en="Barge-in" row>
      <UiToggle :model-value="s.ed().vad.barge_in" @update:model-value="v => (s.ed().vad.barge_in = v)" />
    </SettingsField>
    <p class="wk-hint">播报期间默认停麦；开启后可开口打断。播报结束后 1.2 秒内的音频仍会被丢弃（回声护栏）。</p>

    <UiDisclosure v-model="privacyOpen" class="wk-privacy">
      <template #head>
        <span class="wk-privacy-head">隐私边界 <i>Privacy</i> · 转写模式：{{ asrModeLabel }}</span>
      </template>
      <template #collapsed>
        <span class="wk-hint">音频去向随「识别」页的转写模式变化，点击查看完整说明。</span>
      </template>
      <div class="wk-privacy-body">
        <p class="wk-hint">
          <strong>转写模式＝{{ asrModeLabel }}</strong>：{{ asrPrivacyLine }}。
        </p>
        <p class="wk-hint">
          <strong>云端</strong>时每个 VAD 判到的人声段都会上传到 ASR 服务商——<strong>无论是否说出唤醒词</strong>；
          <strong>本地</strong>模式 VAD/KWS/ASR 全在本机，音频不出本机；
          <strong>混合</strong>仅在本机失败或转写为空时上传兜底。不接受上传请切到本地，或改用文字输入。
        </p>
      </div>
    </UiDisclosure>
  </SettingsCard>
</template>

<script setup lang="ts">
/**
 * 唤醒页：唤醒词、交互时序与行为。灵敏度不再放在这里 —— 真正生效的是
 * `voice.kws.keywords_threshold`，统一在「识别」页的 KWS 模型参数里调整。
 *
 * Wake page: words, timing and behaviour. Sensitivity is not here — the effective knob is
 * `voice.kws.keywords_threshold`, adjusted on the Recognition tab.
 */
import { computed, ref } from 'vue'
import SettingsField from './SettingsField.vue'
import SettingsCard from './SettingsCard.vue'
import SettingsButton from './SettingsButton.vue'
import { UiDisclosure, UiInput, UiStatusDot, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { useVoiceModuleStatus } from '../../../composables/useVoiceModuleStatus'
import { notify } from '../../../composables/useToast'

defineEmits<{ navigate: [tab: 'recognition'] }>()

const s = useSettings()
const { status } = useVoiceModuleStatus()
const privacyOpen = ref(false)

/** ASR 转写模式标签。ASR mode label. */
const asrModeLabel = computed(() => {
  const m = s.sec('asr')?.mode
  return m === 'local' ? '本地' : m === 'hybrid' ? '混合' : '云端'
})

/** 转写模式隐私口径（与识别页一致）。Privacy line for the ASR mode. */
const asrPrivacyLine = computed(() => {
  switch (s.sec('asr')?.mode) {
    case 'local': return '唤醒链与作答/指令段的音频在本机转写、不上云'
    case 'hybrid': return '本地优先，本地不可用/转写为空时才回落云端'
    default: return '音频上传到当前 ASR profile 的服务商'
  }
})

/** 本地 KWS 状态。Local KWS state. */
const kws = computed(() => status.value?.kws)
const kwsReady = computed(() => !!kws.value?.ready)
const kwsModeLabel = computed(() => {
  const mode = kws.value?.mode
  if (mode === 'local') return '本地 KWS'
  if (mode === 'api') return '文本判定'
  if (mode === 'off') return '唤醒关闭'
  return 'KWS 未检测'
})
const kwsToneColor = computed(() => (kwsReady.value ? '#34d399' : '#f87171'))
const kwsDetail = computed(() => {
  const threshold = s.ed()?.kws?.keywords_threshold
  const parts = [kwsReady.value ? '就绪' : '未就绪']
  if (threshold != null) parts.push(`阈值 ${threshold}`)
  return parts.join(' · ')
})
/** 完整模型目录（悬停查看）。Full model directory (shown on hover). */
const kwsModelTitle = computed(() =>
  String(kws.value?.model_dir || '').split(/[\\/]/).pop() || '')

/** 数值输入：保留空串。Numeric input helper. */
function toNum(v: string): number | '' {
  return v === '' ? '' : Number(v)
}

/** 保存：剔除空唤醒词；全空拒绝（避免唤醒永久静默失效）。Save wake settings. */
function saveVoice(): void {
  const list: unknown = s.ed()?.wake_word?.keywords
  if (!Array.isArray(list)) { void s.saveModule('voice'); return }
  const cleaned = list.map((k) => String(k ?? '').trim()).filter(Boolean)
  if (!cleaned.length) {
    notify.err('唤醒词不能全部为空：清空后唤醒将永远不会命中；要停用请关闭「唤醒启用」')
    return
  }
  s.ed().wake_word.keywords = cleaned
  void s.saveModule('voice')
}
</script>

<style scoped>
.wk-status {
  display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border-soft);
  border-radius: var(--r-sm); background: rgba(15, 23, 42, .45);
}
.wk-status-main { display: flex; align-items: center; gap: var(--sp-2); min-width: 0; }
.wk-status-main b { font-size: var(--fs-xs); color: var(--text-1); }
.wk-status-detail { font-size: var(--fs-2xs); color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-section {
  margin: var(--sp-2) 0 0; padding-top: var(--sp-2);
  border-top: var(--divider-dashed);
  font-size: var(--fs-xs); color: var(--text-1); font-weight: 600; letter-spacing: .03em;
}
.wk-section i { font-style: normal; font-weight: 400; color: var(--text-3); margin-left: var(--sp-q6); font-size: var(--fs-2xs); }
.wk-kwrow { display: flex; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-2); }
.wk-kwrow :deep(.ui-input) { flex: 1; min-width: 0; }
.wk-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--sp-2) var(--sp-3); }
.wk-hint { margin: 0; font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; }
.wk-privacy { margin-top: var(--sp-1); }
.wk-privacy-head { font-size: var(--fs-2xs); color: var(--text-2); }
.wk-privacy-head i { font-style: normal; color: var(--text-3); }
.wk-privacy-body { display: flex; flex-direction: column; gap: var(--sp-1); padding-top: var(--sp-1); }
.wk-privacy-body strong { color: var(--text-2); }
</style>
