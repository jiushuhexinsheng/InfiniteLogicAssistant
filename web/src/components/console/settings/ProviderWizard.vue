<template>
  <!-- 新增/编辑供应商向导：第 1 步身份与校验，第 2 步连接与模型。
       Add/edit provider wizard: step 1 identity + validation, step 2 connection + models. -->
  <UiModal :model-value="modelValue" :title="title" @update:model-value="v => emit('update:modelValue', v)">
    <div v-if="step === 1" class="pw-form">
      <p class="pw-hint">选择内置供应商，或自定义 Provider ID / Base URL / 协议。</p>
      <div class="pw-presets">
        <button
          v-for="p in presets" :key="p.id" type="button" class="pw-preset"
          @click="choosePreset(p)"
        >
          <b>{{ p.name }}</b>
          <span>{{ p.protocol }}</span>
        </button>
      </div>

      <SettingsField label="Provider ID" en="Provider ID" hint="小写标识，保存后作为 profile 名">
        <UiInput
          v-model="form.id"
          :disabled="!!editing"
          placeholder="例如 my-provider"
        />
        <p v-if="idError" class="pw-err">{{ idError }}</p>
      </SettingsField>
      <SettingsField label="协议" en="Protocol">
        <UiSelect v-model="form.protocol" :options="protocolOptions" />
      </SettingsField>
      <SettingsField label="Base URL" en="Base URL">
        <UiInput v-model="form.endpoint" placeholder="https://api.example.com" />
        <p v-if="urlError" class="pw-err">{{ urlError }}</p>
      </SettingsField>

      <div class="pw-actions">
        <SettingsButton variant="secondary" zh="取消" en="Cancel" @click="close" />
        <span v-if="firstError" class="pw-err pw-next-why">{{ firstError }}</span>
        <SettingsButton
          variant="primary" class="pw-next" :disabled="!!firstError"
          zh="下一步" en="Next" @click="step = 2"
        />
      </div>
    </div>

    <div v-else class="pw-form">
      <p class="pw-hint">{{ form.id }} · {{ form.protocol }} · {{ form.endpoint }}</p>

      <SettingsField label="API Key" en="API Key" hint="只写不读；保存时写入 secrets 文件">
        <UiChip v-if="keySet && !apiKey" tone="ok" :dot="false">Key 已设置（留空则不修改）</UiChip>
        <UiInput v-model="apiKey" class="pw-key" type="password" placeholder="sk-..." />
      </SettingsField>

      <div class="pw-fetchrow">
        <SettingsButton
          variant="secondary" class="pw-fetch" :disabled="fetching"
          :zh="fetching ? '获取中…' : '获取模型'" :en="fetching ? 'Fetching…' : 'Fetch models'"
          @click="fetchModels"
        />
        <span v-if="fetchError" class="pw-err">{{ fetchError }}</span>
      </div>

      <FetchedModelList
        v-if="fetched.length"
        :models="fetched"
        :added="models"
        @add="addFetched"
      />

      <SettingsField label="模型列表" en="Models" hint="至少一个；获取失败可手动输入">
        <ModelTable
          :models="models"
          :options="modelOptions"
          @update:models="v => (models = v)"
        />
      </SettingsField>

      <div class="pw-actions">
        <SettingsButton variant="secondary" zh="上一步" en="Back" @click="step = 1" />
        <SettingsButton
          variant="primary" class="pw-save"
          :disabled="!models.length || saving" :loading="saving"
          :zh="saving ? '保存中…' : '保存供应商'" :en="saving ? 'Saving…' : 'Save provider'"
          @click="save"
        />
      </div>
    </div>
  </UiModal>
</template>

<script setup lang="ts">
/**
 * 供应商向导。校验文案常驻字段下方；Next 禁用时旁边显示第一条原因（不再静默）。
 * 编辑模式 ID 只读（改名会留下旧 secrets 与历史引用）。
 *
 * Provider wizard: validation copy lives under each field; when Next is disabled the
 * first reason is shown beside it (no more silent disabling). Edit mode keeps the ID
 * read-only (renaming would orphan secrets and history references).
 */
import { computed, reactive, ref, watch } from 'vue'
import SettingsField from './SettingsField.vue'
import FetchedModelList from './FetchedModelList.vue'
import ModelTable from './ModelTable.vue'
import { UiChip, UiInput, UiModal, UiSelect } from '../../ui'
import SettingsButton from './SettingsButton.vue'
import { api } from '../../../api'
import { presetsFor, type ProviderPreset, type ProviderSection } from './providerPresets'
import { useSettings } from './useSettings'
import { notify } from '../../../composables/useToast'

const props = withDefaults(defineProps<{
  modelValue: boolean
  section: ProviderSection
  editingId?: string | null
  profiles?: Record<string, any>
  keySet?: boolean
}>(), { editingId: null, profiles: () => ({}), keySet: false })

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  saved: [id: string]
  close: []
}>()

const s = useSettings()
const step = ref<1 | 2>(1)
const editing = ref('')
const form = reactive({ id: '', protocol: 'openai', endpoint: '' })
const apiKey = ref('')
const models = ref<string[]>([])
const fetched = ref<string[]>([])
const fetching = ref(false)
const saving = ref(false)
const fetchError = ref('')

const presets = computed(() => presetsFor(props.section))
const protocolOptions = computed(() => props.section === 'llm'
  ? [
      { value: 'openai', label: 'OpenAI Chat Completions' },
      { value: 'anthropic', label: 'Anthropic Messages' },
      { value: 'gemini', label: 'Gemini' },
    ]
  : [{ value: 'openai', label: 'OpenAI 兼容 / Compatible' }])

const title = computed(() => editing.value
  ? '编辑供应商 / Edit Provider'
  : (step.value === 1 ? '新增供应商 · 选择 / Provider' : '新增供应商 · 连接与模型 / Connection & Models'))

/** ID 校验。ID validation. */
const idError = computed(() => {
  // 编辑模式 ID 只读：跳过格式/重名校验，否则非规范命名的旧 profile 会被卡死。
  if (editing.value) return ''
  const id = form.id.trim()
  if (!id) return '请填写 Provider ID'
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(id)) return '只能小写字母/数字/-/_，且以字母或数字开头'
  if (!editing.value && props.profiles[id]) return '该 ID 已被使用——从列表点击它进入编辑'
  return ''
})

/** URL 校验。URL validation. */
const urlError = computed(() => {
  const url = form.endpoint.trim()
  if (!url) return '请填写 Base URL'
  if (!/^https?:\/\//.test(url)) return '需要以 http:// 或 https:// 开头'
  return ''
})

/** 第一条错误（按钮旁显示）。First error, shown beside the button. */
const firstError = computed(() => idError.value || urlError.value)

/** 模型并集：当前 model 在前，再接 models（去空去重）。Current model first, then models. */
function unionModels(listed: string[] | undefined, current: string | undefined): string[] {
  const out: string[] = []
  for (const raw of [current || '', ...(listed || [])]) {
    const value = String(raw || '').trim()
    if (value && !out.includes(value)) out.push(value)
  }
  return out
}

/** 打开/切换编辑对象时重置表单。Reset the form when opened or the edit target changes. */
watch(() => [props.modelValue, props.editingId] as const, ([open, editingId]) => {
  if (!open) return
  step.value = 1
  editing.value = editingId || ''
  const profile = editingId ? props.profiles[editingId] : null
  form.id = editingId || ''
  form.protocol = profile?.provider || 'openai'
  form.endpoint = profile?.endpoint || ''
  apiKey.value = ''
  fetched.value = []
  fetchError.value = ''
  models.value = unionModels(profile?.models, profile?.model)
}, { immediate: true })

/** 模型输入候选：拉取结果 ∪ 当前表格。Combobox options: fetched ∪ current table. */
const modelOptions = computed(() => {
  const out = [...fetched.value]
  for (const m of models.value) if (m && !out.includes(m)) out.push(m)
  return out
})

/** 预设：填表并进入第 2 步；已存在的 ID 转为编辑该供应商。Preset fill. */
function choosePreset(preset: ProviderPreset): void {
  form.id = preset.id
  form.protocol = preset.protocol
  form.endpoint = preset.endpoint
  if (props.profiles[preset.id]) {
    editing.value = preset.id
    const existing = props.profiles[preset.id]
    models.value = unionModels(existing.models, existing.model)
  } else {
    // 编辑 A 时点一个不存在的预设 = 改为新增：不能继承 A 的字段。
    editing.value = ''
    models.value = [...(preset.models || [])]
  }
  step.value = 2
}

/** 拉取模型列表（不清空已有表格）。Fetch models without touching the configured table. */
async function fetchModels(): Promise<void> {
  fetching.value = true
  fetchError.value = ''
  try {
    const existing = editing.value ? (props.profiles[editing.value] || {}) : {}
    const r = await api.fetchModels(props.section, {
      name: form.id,
      provider: form.protocol,
      endpoint: form.endpoint,
      chat_path: existing.chat_path
        || (form.protocol === 'anthropic' ? '/v1/messages' : '/v1/chat/completions'),
      api_key: apiKey.value,
      api_key_env: existing.api_key_env || '',
      models_path: existing.models_path || '',
      timeout: 30,
    })
    if (r.ok && r.models?.length) {
      fetched.value = r.models
    } else {
      fetchError.value = r.error || '获取模型失败，可手动输入模型 ID'
    }
  } catch (e: any) {
    fetchError.value = e?.message || '获取模型失败，可手动输入模型 ID'
  } finally {
    fetching.value = false
  }
}

/** 把勾选到的模型并入表格。Merge picked models into the table. */
function addFetched(picked: string[]): void {
  models.value = unionModels([...models.value, ...picked], '')
}

/** 关闭并抛 close。Close and emit. */
function close(): void {
  emit('update:modelValue', false)
  emit('close')
}

/** 保存：保留未被向导编辑的字段，只覆盖身份/模型，并按需写密钥。Save provider. */
async function save(): Promise<void> {
  if (!models.value.length || saving.value) return
  saving.value = true
  try {
    const id = form.id.trim()
    const existing = editing.value ? (props.profiles[editing.value] || {}) : {}
    const listed = [...models.value]
    const current = String(existing.model || '')
    const profile: Record<string, any> = {
      ...existing,
      provider: form.protocol,
      endpoint: form.endpoint.trim(),
      // 编辑时保留自定义路径（TTS 的 speech/chat 模式由它决定）。
      chat_path: existing.chat_path
        || (form.protocol === 'anthropic' ? '/v1/messages' : '/v1/chat/completions'),
      models: listed,
      model: current && listed.includes(current) ? current : listed[0],
    }
    if (props.section === 'asr' && !profile.language) profile.language = 'zh'
    if (props.section === 'tts') {
      profile.format = profile.format || 'wav'
      profile.voice = profile.voice || ''
      profile.voices = profile.voices || []
    }

    const snapshot = s.editable.value
    if (!snapshot) return
    const section = (snapshot as any)[props.section]
    // 赋值前记录：赋值后 keys 已包含新 id，条件永远为 false。
    const hadProfiles = Object.keys(props.profiles).length > 0
    section.profiles[id] = profile
    // 只有「一份 profile 都没有」时才自动设为 active，避免静默切走当前模型。
    if (!hadProfiles) section.active = id
    if (apiKey.value) {
      try {
        await api.putSecret(`${props.section}.profiles.${id}`, apiKey.value)
      } catch (e: any) {
        notify.err('密钥写入失败：' + (e?.message || e))
        return
      }
    }
    await s.saveModule(props.section)

    emit('saved', id)
    emit('update:modelValue', false)
    emit('close')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.pw-form { display: flex; flex-direction: column; gap: var(--sp-3); }
.pw-hint { margin: 0; font-size: var(--fs-2xs); color: var(--text-3); }
.pw-presets { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
.pw-preset {
  display: flex; flex-direction: column; gap: 1px; padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  background: rgba(15, 23, 42, .5); color: var(--text-1); cursor: pointer;
}
.pw-preset:hover { border-color: var(--brand-c2); }
.pw-preset span { font-size: var(--fs-2xs); color: var(--text-3); }
.pw-fetchrow { display: flex; align-items: center; gap: var(--sp-2); }
.pw-err { margin: var(--sp-q6) 0 0; font-size: var(--fs-2xs); color: #f87171; }
.pw-next-why { margin: 0 var(--sp-1) 0 0; }
.pw-actions { display: flex; align-items: center; justify-content: flex-end; gap: var(--sp-2); }
</style>
