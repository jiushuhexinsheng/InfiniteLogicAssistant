<template>
  <!-- 服务模块卡：LLM / ASR / TTS 共用（字段表由 sectionDefs 驱动）。
       Service module card: shared by LLM / ASR / TTS, fields driven by sectionDefs.
       模型列表由供应商向导维护；本卡只编辑「编辑对象」profile 的其余字段。 -->
  <SettingsCard :title="section.title" :title-en="section.titleEn">
    <template #actions>
      <div class="cs-card-btns">
        <DetectionStatusDot :status="detectionStatus" :detail="detectionDetail" />
        <!-- 测试连接：进行中显示「测试中…」；结果 toast 之外，旁边状态点持续可见。 -->
        <UiButton variant="secondary" size="sm" :disabled="s.detecting.value" @click="s.detectOne(section.name)">
          <UiIcon v-if="s.detecting.value" name="loader-2" :size="12" class="cs-spin" />
          <BiLabel :zh="s.detecting.value ? '测试中…' : T.testConnection.zh"
                   :en="s.detecting.value ? 'Testing…' : T.testConnection.en" />
        </UiButton>
        <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule(section.key)">
          <BiLabel :zh="s.saving.value ? T.saving.zh : T.save.zh"
                   :en="s.saving.value ? T.saving.en : T.save.en" />
        </UiButton>
      </div>
    </template>

    <SettingsField v-if="section.toggle" label="启用" row>
      <UiToggle :model-value="s.sec(section.key).enabled" @update:model-value="v => (s.sec(section.key).enabled = v)" />
    </SettingsField>

    <p v-if="section.key === 'asr'" class="cs-note">
      转写模式（本地 / 云端 / 混合）与本地模型在上方「识别引擎」卡设置；本卡只配置云端 API Profile。
    </p>

    <!-- 编辑对象：只决定本卡编辑哪个 profile，不写 active（切换全局模型在对话里）。 -->
    <div class="cs-profrow">
      <SettingsField label="编辑对象" en="Editing" grow>
        <UiSelect v-model="editTarget" :options="profileOptions" />
      </SettingsField>
    </div>

    <template v-for="f in section.fields" :key="f">
      <SettingsField :label="fieldLabel(f)" :en="fieldLabelEn(f)">
        <UiSelect v-if="f === 'provider'" :model-value="profile()[f]" :options="PROVIDERS" @update:model-value="v => (profile()[f] = v)" />
        <UiSelect v-else-if="f === 'format'" :model-value="profile()[f]" :options="FORMATS" @update:model-value="v => (profile()[f] = v)" />
        <UiCombobox
          v-else-if="f === 'voice'"
          :model-value="profile()[f]"
          :options="s.voiceOptions(section)"
          @update:model-value="v => (profile()[f] = v)"
        />
        <template v-else-if="f === 'voices'">
          <div v-for="(_, i) in (profile().voices || [])" :key="i" class="cs-voicerow">
            <UiInput :model-value="profile().voices[i]" @update:model-value="v => (profile().voices[i] = v)" placeholder="如 alloy" />
            <UiButton variant="secondary" size="sm" hover="danger" @click="profile().voices.splice(i, 1)">删除</UiButton>
          </div>
          <UiButton variant="secondary" size="sm" @click="addVoice">＋ 新增音色</UiButton>
        </template>
        <UiInput
          v-else
          :model-value="profile()[f]"
          @update:model-value="v => (profile()[f] = v)"
          :type="isNumericField(f) ? 'number' : 'text'"
          :step="isNumericField(f) ? (f === 'temperature' ? 0.1 : 1) : undefined"
        />
      </SettingsField>
    </template>

    <div class="cs-keyrow">
      <UiChip :tone="s.sec(section.key).api_key_set[editTarget] ? 'ok' : 'warn'" :dot="false">
        API Key：{{ s.sec(section.key).api_key_set[editTarget] ? '已设置' : '未设置' }}
      </UiChip>
      <UiButton variant="secondary" size="sm" @click="s.openKeyModal(section.key, editTarget)">设置</UiButton>
    </div>

    <!-- 高级兼容：键值行；内置快捷项并入键 combobox（不再是独立 chip 行）。 -->
    <div class="cs-compat">
      <div class="cs-compat-head">
        <span class="cs-compat-title">高级兼容</span>
        <span class="cs-compat-hint">特殊网关的请求体补丁（键可选内置项或手输）</span>
      </div>
      <CompatEditor :entries="s.compatEntries(section)" @update="setCompatEntries" />
    </div>

    <slot />
  </SettingsCard>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SettingsField from './SettingsField.vue'
import SettingsCard from './SettingsCard.vue'
import CompatEditor from './CompatEditor.vue'
import DetectionStatusDot from './DetectionStatusDot.vue'
import { UiButton, UiChip, UiCombobox, UiIcon, UiInput, UiSelect, UiToggle } from '../../ui'
import BiLabel from './BiLabel.vue'
import { settingsText as T } from '../../../locales/settings'
import type { SegOption } from '../../ui/UiSegmented.vue'
import { useSettings } from './useSettings'
import { fieldLabel, fieldLabelEn, isNumericField, type SectionDef } from './configDefs'

/** 组件 props：服务模块定义（来自 configDefs.sectionDefs）。Service section definition. */
const props = defineProps<{ section: SectionDef }>()

/** 设置页单例状态与操作。Settings singleton. */
const s = useSettings()

/** 协议下拉选项。Protocol options. */
const PROVIDERS: SegOption[] = [
  { value: 'openai', label: 'OpenAI 兼容' },
  { value: 'anthropic', label: 'Anthropic（原生）' },
  { value: 'gemini', label: 'Gemini（原生）' },
]

/** 音频格式下拉选项。Audio format options. */
const FORMATS: SegOption[] = [
  { value: 'wav', label: 'wav' },
  { value: 'mp3', label: 'mp3' },
  { value: 'pcm16', label: 'pcm16' },
]

/** 本卡编辑对象（本地状态，不写 active）。The card's editing target (local, never persisted as active). */
const editTarget = ref('')

/** 当前 section 的 profiles。Profiles of this section. */
const profiles = computed<Record<string, any>>(() => s.sec(props.section.key)?.profiles || {})

/** 运行时解析后的 active（空串 → 第一个 profile）。Resolved active profile id. */
const resolvedActive = computed(() => {
  const sec = s.sec(props.section.key)
  if (!sec) return ''
  return sec.active && sec.profiles?.[sec.active] ? sec.active : (Object.keys(sec.profiles || {})[0] || '')
})

watch([resolvedActive, () => props.section.key], () => {
  if (!editTarget.value || !profiles.value[editTarget.value]) editTarget.value = resolvedActive.value
}, { immediate: true })

/** 正在编辑的 profile 对象。The profile object being edited. */
function profile(): any {
  return profiles.value[editTarget.value] || {}
}

/** Profile 下拉选项。Profile options. */
const profileOptions = computed<SegOption[]>(() =>
  Object.keys(profiles.value).map(n => ({ value: n, label: n })),
)

/** 连通性结果（测试连接状态点）。Connectivity result for the status dot. */
const conn = computed(() => s.connResults.value[props.section.name])
const detectionStatus = computed<'idle' | 'testing' | 'ok' | 'fail'>(() => {
  if (s.detecting.value) return 'testing'
  if (!conn.value) return 'idle'
  return conn.value.status === 'ok' ? 'ok' : 'fail'
})
const detectionDetail = computed(() => {
  if (!conn.value) return '尚未测试连接'
  const label = conn.value.status === 'ok' ? '上次检测：成功' : '上次检测：失败'
  return conn.value.latency_ms != null ? `${label} · ${conn.value.latency_ms}ms` : label
})

/** 把兼容编辑器回传的键值行写回 profile.compat。Write compat rows back to the profile. */
function setCompatEntries(entries: Array<[string, string]>): void {
  const prof = profile()
  prof.compat = Object.fromEntries(entries.filter(([k]) => k.trim()))
}

/** 向 profile.voices 追加一个空音色行。Append an empty voice row. */
function addVoice(): void {
  const prof = profile()
  if (!Array.isArray(prof.voices)) prof.voices = []
  prof.voices.push('')
}
</script>

<style scoped>
.cs-card-btns { display: flex; align-items: center; gap: var(--sp-2); }
.cs-profrow { display: flex; align-items: flex-end; gap: var(--sp-2); }
.cs-keyrow { display: flex; align-items: center; gap: var(--sp-2); }
.cs-voicerow { display: flex; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-2); }
.cs-voicerow :deep(.ui-input) { flex: 1; min-width: 0; }
.cs-compat { border-top: var(--divider-dashed); padding-top: var(--sp-q10); display: flex; flex-direction: column; gap: var(--sp-2); }
.cs-compat-head { display: flex; align-items: baseline; gap: var(--sp-2); }
.cs-compat-title { font-size: var(--fs-2xs); font-weight: 600; color: var(--text-2); letter-spacing: .04em; }
.cs-compat-hint { font-size: var(--fs-2xs); color: var(--text-3); }
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: var(--sp-1) 0 0; }
.cs-spin { animation: cs-spin .9s linear infinite; }
@keyframes cs-spin { to { transform: rotate(360deg); } }
</style>
