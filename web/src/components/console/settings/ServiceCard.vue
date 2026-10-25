<template>
  <!-- 服务模块卡：LLM / ASR / TTS 共用（字段表由 sectionDefs 驱动）。
       Service module card: shared by LLM / ASR / TTS, fields driven by sectionDefs.
       模型列表由供应商向导维护；本卡只编辑「编辑对象」profile 的其余字段。 -->
  <SettingsCard :title="section.title" :title-en="section.titleEn">
    <template #actions>
      <div class="cs-card-btns">
        <DetectionStatusDot :status="detectionStatus" :detail="detectionDetail" />
        <!-- 测试连接：进行中显示「测试中…」；结果 toast 之外，旁边状态点持续可见。 -->
        <SettingsButton
          variant="secondary" :loading="s.detecting.value"
          :zh="s.detecting.value ? '测试中…' : '测试连接'"
          :en="s.detecting.value ? 'Testing…' : 'Test connection'"
          @click="s.detectOne(section.name)"
        />
        <SettingsButton
          variant="primary" :disabled="!s.editable.value" :loading="s.saving.value"
          :zh="s.saving.value ? '保存中…' : '保存'"
          :en="s.saving.value ? 'Saving…' : 'Save'"
          @click="s.saveModule(section.key)"
        />
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
          :options="profile().voices || []"
          @update:model-value="v => (profile()[f] = v)"
        />
        <template v-else-if="f === 'voices'">
          <div v-for="(_, i) in (profile().voices || [])" :key="i" class="cs-voicerow">
            <UiInput :model-value="profile().voices[i]" @update:model-value="v => (profile().voices[i] = v)" placeholder="如 alloy" />
            <SettingsButton variant="secondary" hover="danger" zh="删除" en="Delete" @click="profile().voices.splice(i, 1)" />
          </div>
          <SettingsButton variant="secondary" zh="新增音色" en="Add voice" @click="addVoice" />
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
      <UiChip :tone="keySet ? 'ok' : 'warn'" :dot="false">
        API Key：{{ keySet ? '已设置' : '未设置' }}
      </UiChip>
      <SettingsButton zh="设置密钥" en="Set key" @click="s.openKeyModal(section.key, editTarget)" />
    </div>

    <!-- 模型管理（与供应商向导共用 ModelTable / FetchedModelList 组件）。 -->
    <div class="cs-models">
      <div class="cs-models-head">
        <span class="cs-models-title">模型列表 · Models</span>
        <SettingsButton
          variant="secondary" class="cs-fetch" :disabled="fetching"
          :zh="fetching ? '获取中…' : '获取模型'" :en="fetching ? 'Fetching…' : 'Fetch models'"
          @click="fetchModels"
        />
        <span v-if="fetchError" class="cs-err">{{ fetchError }}</span>
      </div>
      <ModelTable :models="modelList" :options="modelOptions" @update:models="setModels" />
      <FetchedModelDialog
        v-model="fetchedOpen"
        :models="fetched"
        :added="modelList"
        @add="addFetched"
      />
    </div>

    <!-- 高级兼容：键值行；内置快捷项并入键 combobox（不再是独立 chip 行）。 -->
    <div class="cs-compat">
      <div class="cs-compat-head">
        <span class="cs-compat-title">高级兼容</span>
        <span class="cs-compat-hint">特殊网关的请求体补丁（键可选内置项或手输）</span>
      </div>
      <CompatEditor :entries="compatRows" @update="setCompatEntries" />
    </div>

    <slot />
  </SettingsCard>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SettingsField from './SettingsField.vue'
import SettingsCard from './SettingsCard.vue'
import CompatEditor from './CompatEditor.vue'
import FetchedModelDialog from './FetchedModelDialog.vue'
import ModelTable from './ModelTable.vue'
import SettingsButton from './SettingsButton.vue'
import DetectionStatusDot from './DetectionStatusDot.vue'
import { UiChip, UiCombobox, UiInput, UiSelect, UiToggle } from '../../ui'
import type { SegOption } from '../../ui/UiSegmented.vue'
import { useSettings } from './useSettings'
import { fieldLabel, fieldLabelEn, isNumericField, type SectionDef } from './configDefs'
import { parseCompatValue } from './profiles'
import { api } from '../../../api'

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

/** 编辑对象是否已设置密钥（快照切换时安全）。Whether the edit target has a key. */
const keySet = computed(() => !!s.sec(props.section.key)?.api_key_set?.[editTarget.value])

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

/** 当前编辑对象的兼容行（不得读 active profile）。Compat rows of the editing target. */
const compatRows = computed<Array<[string, string]>>(() =>
  Object.entries(profile().compat || {}).map(
    ([k, v]) => [k, typeof v === 'string' ? v : String(v)] as [string, string],
  ),
)

/** 把兼容编辑器回传的键值行写回编辑对象，并恢复布尔/数字类型。 */
function setCompatEntries(entries: Array<[string, string]>): void {
  const prof = profile()
  prof.compat = Object.fromEntries(
    entries.filter(([k]) => k.trim()).map(([k, v]) => [k, parseCompatValue(v)]),
  )
}

/** 拉取结果与错误（模型管理块）。Fetched models and error for the model block. */
const fetched = ref<string[]>([])
const fetchedOpen = ref(false)
const fetching = ref(false)
const fetchError = ref('')

/** 编辑对象的模型列表（当前 model 在前，再接 models）。Models of the editing target. */
const modelList = computed<string[]>(() => {
  const prof = profile()
  const out: string[] = []
  for (const raw of [prof.model || '', ...(prof.models || [])]) {
    const value = String(raw || '').trim()
    if (value && !out.includes(value)) out.push(value)
  }
  return out
})

/** 模型输入候选：拉取结果 ∪ 当前列表。Combobox options: fetched ∪ current. */
const modelOptions = computed<string[]>(() => {
  const out = [...fetched.value]
  for (const m of modelList.value) if (!out.includes(m)) out.push(m)
  return out
})

/** 写回模型列表；当前模型被删时回落到第一项。Write models back; fall back when current removed. */
function setModels(list: string[]): void {
  const prof = profile()
  const clean: string[] = []
  for (const raw of list) {
    const value = String(raw || '').trim()
    if (value && !clean.includes(value)) clean.push(value)
  }
  prof.models = clean
  if (!clean.includes(prof.model)) prof.model = clean[0] || ''
}

/** 把勾选到的模型并入列表。Merge picked models. */
function addFetched(picked: string[]): void {
  setModels([...modelList.value, ...picked])
}

/** 拉取模型（带 profile name，服务端按 secrets 解析已存密钥）。Fetch models. */
async function fetchModels(): Promise<void> {
  const prof = profile()
  fetching.value = true
  fetchError.value = ''
  try {
    const r = await api.fetchModels(props.section.key, {
      ...prof,
      name: editTarget.value,
      api_key: '',
    })
    if (r.ok && r.models?.length) {
      fetched.value = r.models
      fetchedOpen.value = true
    } else {
      fetchError.value = r.error || '获取模型失败，可手动输入模型 ID'
    }
  } catch (e: any) {
    fetchError.value = e?.message || '获取模型失败，可手动输入模型 ID'
  } finally {
    fetching.value = false
  }
}

// 切换编辑对象时清空上一次的拉取结果。Clear fetched results when the edit target changes.
watch(editTarget, () => {
  fetched.value = []
  fetchError.value = ''
})

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
.cs-models { border-top: var(--divider-dashed); padding-top: var(--sp-q10); display: flex; flex-direction: column; gap: var(--sp-2); }
.cs-models-head { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
.cs-models-title { font-size: var(--fs-2xs); font-weight: 600; color: var(--text-2); letter-spacing: .04em; }
.cs-err { font-size: var(--fs-2xs); color: #f87171; }
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
