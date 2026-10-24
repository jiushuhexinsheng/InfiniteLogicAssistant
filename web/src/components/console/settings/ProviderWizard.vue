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
          :disabled="editing"
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
        <UiButton variant="secondary" size="sm" @click="close">取消 / Cancel</UiButton>
        <span v-if="firstError" class="pw-err pw-next-why">{{ firstError }}</span>
        <UiButton variant="primary" size="sm" class="pw-next" :disabled="!!firstError" @click="step = 2">
          下一步 / Next
        </UiButton>
      </div>
    </div>

    <div v-else class="pw-form">
      <p class="pw-hint">{{ form.id }} · {{ form.protocol }} · {{ form.endpoint }}</p>
      <p class="pw-hint">连接与模型配置将在下一步补齐。</p>
      <div class="pw-actions">
        <UiButton variant="secondary" size="sm" @click="step = 1">上一步 / Back</UiButton>
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
import { UiButton, UiInput, UiModal, UiSelect } from '../../ui'
import { presetsFor, type ProviderPreset, type ProviderSection } from './providerPresets'

const props = withDefaults(defineProps<{
  modelValue: boolean
  section: ProviderSection
  editingId?: string | null
  profiles?: Record<string, any>
}>(), { editingId: null, profiles: () => ({}) })

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  saved: [id: string]
  close: []
}>()

const step = ref<1 | 2>(1)
const editing = ref('')
const form = reactive({ id: '', protocol: 'openai', endpoint: '' })

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

/** 打开/切换编辑对象时重置表单。Reset the form when opened or the edit target changes. */
watch(() => [props.modelValue, props.editingId] as const, ([open, editingId]) => {
  if (!open) return
  step.value = 1
  editing.value = editingId || ''
  const profile = editingId ? props.profiles[editingId] : null
  form.id = editingId || ''
  form.protocol = profile?.provider || 'openai'
  form.endpoint = profile?.endpoint || ''
}, { immediate: true })

/** 预设：填表并进入第 2 步；已存在的 ID 转为编辑该供应商。Preset fill. */
function choosePreset(preset: ProviderPreset): void {
  form.id = preset.id
  form.protocol = preset.protocol
  form.endpoint = preset.endpoint
  if (props.profiles[preset.id]) editing.value = preset.id
  step.value = 2
}

/** 关闭并抛 close。Close and emit. */
function close(): void {
  emit('update:modelValue', false)
  emit('close')
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
.pw-err { margin: var(--sp-q6) 0 0; font-size: var(--fs-2xs); color: #f87171; }
.pw-next-why { margin: 0 var(--sp-1) 0 0; }
.pw-actions { display: flex; align-items: center; justify-content: flex-end; gap: var(--sp-2); }
</style>
