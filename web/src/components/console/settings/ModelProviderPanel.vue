<template>
  <!-- 模型供应商：列表 + 添加向导（选择供应商 → 连接/获取模型 → 保存）。
       Model providers: list + add wizard (provider → connection/models → save).
       大模型 / ASR / TTS 共用同一个组件，只按 section 过滤 preset 与协议。 -->
  <SettingsCard title="模型供应商" title-en="Model Providers">
    <template #actions>
      <UiButton variant="secondary" size="sm" @click="openWizard">
        <BiLabel zh="新增供应商" en="Add Provider" />
      </UiButton>
    </template>

    <div v-if="providers.length" class="mp-list">
      <button
        v-for="p in providers"
        :key="p.id"
        type="button"
        class="mp-item"
        :class="{ on: p.id === active }"
        @click="activate(p.id)"
      >
        <span class="mp-name">{{ p.name || p.id }}</span>
        <span class="mp-meta">{{ p.protocol || 'openai' }} · {{ p.models.length }} 模型</span>
        <span class="mp-url">{{ p.endpoint || '未填 Endpoint' }}</span>
        <span class="mp-key" :class="{ set: p.keySet }">{{ p.keySet ? 'Key 已设置' : 'Key 未设置' }}</span>
        <span v-if="p.id === active" class="mp-active">当前 / Active</span>
        <span class="mp-del" role="button" title="删除供应商" @click.stop="removeProvider(p.id)">×</span>
      </button>
    </div>
    <p v-else class="cs-hint">还没有供应商。点击「新增供应商 / Add Provider」开始；已有自填 profile 也会显示在这里。</p>

    <UiModal v-model="wizard" :title="step === 1 ? '新增供应商 · 选择 / Provider' : '新增供应商 · 连接与模型 / Connection & Models'">
      <div v-if="step === 1" class="mp-form">
        <p class="cs-hint">选择内置供应商，或自定义 Provider ID / Base URL / 协议。</p>
        <div class="mp-presets">
          <button v-for="p in presets" :key="p.id" type="button" class="mp-preset" @click="choosePreset(p)">
            <b>{{ p.name }}</b>
            <span>{{ p.protocol }}</span>
          </button>
        </div>
        <SettingsField label="Provider ID" en="Provider ID" hint="小写标识，保存后作为 profile 名" hint-en="Lowercase id; becomes the profile name">
          <UiInput v-model="form.id" placeholder="例如 my-provider" />
        </SettingsField>
        <SettingsField label="协议" en="Protocol">
          <UiSelect v-model="form.protocol" :options="protocolOptions" />
        </SettingsField>
        <SettingsField label="Base URL" en="Base URL">
          <UiInput v-model="form.endpoint" placeholder="https://api.example.com" />
        </SettingsField>
        <div class="mp-actions">
          <UiButton variant="secondary" size="sm" @click="wizard = false">取消 / Cancel</UiButton>
          <UiButton variant="primary" size="sm" :disabled="!step1Valid" @click="step = 2">下一步 / Next</UiButton>
        </div>
      </div>

      <div v-else class="mp-form">
        <p class="cs-hint">{{ form.id }} · {{ form.protocol }} · {{ form.endpoint }}</p>
        <SettingsField label="API Key" en="API Key" hint="只写不读；保存时写入 secrets 文件" hint-en="Write-only; stored in the secrets file">
          <UiInput v-model="form.apiKey" type="password" placeholder="sk-..." />
        </SettingsField>
        <div class="mp-fetch">
          <UiButton variant="secondary" size="sm" :disabled="fetching" @click="fetchModels">
            <BiLabel :zh="fetching ? '获取中…' : '获取模型'" :en="fetching ? 'Fetching…' : 'Fetch Models'" />
          </UiButton>
          <span v-if="fetchError" class="mp-err">{{ fetchError }}</span>
        </div>
        <SettingsField label="模型列表" en="Models" hint="至少一个；获取失败可手动输入" hint-en="At least one; manual input works when fetching fails">
          <div class="mp-models">
            <span v-for="m in form.models" :key="m" class="mp-model">
              {{ m }} <span class="mp-model-x" @click="removeModel(m)">×</span>
            </span>
            <span v-if="!form.models.length" class="cs-hint">尚未添加模型</span>
          </div>
          <div class="mp-addmodel">
            <UiInput v-model="form.modelInput" placeholder="model-id" @keyup.enter="addModel" />
            <UiButton variant="secondary" size="sm" @click="addModel">添加 / Add</UiButton>
          </div>
        </SettingsField>
        <div class="mp-actions">
          <UiButton variant="secondary" size="sm" @click="step = 1">上一步 / Back</UiButton>
          <UiButton variant="primary" size="sm" :disabled="!form.models.length || saving" @click="save">
            <BiLabel :zh="saving ? '保存中…' : '保存供应商'" :en="saving ? 'Saving…' : 'Save Provider'" />
          </UiButton>
        </div>
      </div>
    </UiModal>
  </SettingsCard>
</template>

<script setup lang="ts">
/**
 * 供应商配置面板：大模型 / ASR / TTS 复用。
 *
 * 第一层是供应商（endpoint / 协议 / 密钥），第二层才是具体模型；语音页只负责把
 * 选中的模型写入 section，模型参数仍由 ModelConfigCard 处理。
 */
import { computed, reactive, ref } from 'vue'
import SettingsCard from './SettingsCard.vue'
import SettingsField from './SettingsField.vue'
import BiLabel from './BiLabel.vue'
import { UiButton, UiInput, UiModal, UiSelect } from '../../ui'
import { api } from '../../../api'
import { useSettings } from './useSettings'
import { notify } from '../../../composables/useToast'

type Section = 'llm' | 'asr' | 'tts'
interface Preset {
  id: string
  name: string
  protocol: string
  endpoint: string
  sections: Section[]
  models?: string[]
}

const props = defineProps<{ section: Section }>()
const s = useSettings()

const PRESETS: Preset[] = [
  { id: 'openai', name: 'OpenAI', protocol: 'openai', endpoint: 'https://api.openai.com', sections: ['llm', 'asr', 'tts'] },
  { id: 'deepseek', name: 'DeepSeek', protocol: 'openai', endpoint: 'https://api.deepseek.com', sections: ['llm'], models: ['deepseek-chat', 'deepseek-reasoner'] },
  { id: 'anthropic', name: 'Anthropic', protocol: 'anthropic', endpoint: 'https://api.anthropic.com', sections: ['llm'] },
  { id: 'xiaomi-mimo', name: 'Xiaomi MiMo', protocol: 'openai', endpoint: 'https://token-plan-cn.xiaomimimo.com', sections: ['llm', 'asr', 'tts'] },
]
const presets = computed(() => PRESETS.filter(p => p.sections.includes(props.section)))
const protocolOptions = computed(() => props.section === 'llm'
  ? [{ value: 'openai', label: 'OpenAI Chat Completions' }, { value: 'anthropic', label: 'Anthropic Messages' }, { value: 'gemini', label: 'Gemini' }]
  : [{ value: 'openai', label: 'OpenAI 兼容 / Compatible' }])

const sec = computed(() => s.sec(props.section) as any)
const active = computed(() => sec.value?.active || '')
const providers = computed(() => Object.entries(sec.value?.profiles || {}).map(([id, p]: [string, any]) => ({
  id,
  name: p.name || id,
  protocol: p.provider || 'openai',
  endpoint: p.endpoint || '',
  models: p.models || [],
  keySet: !!sec.value?.api_key_set?.[id],
})))

const wizard = ref(false)
const step = ref<1 | 2>(1)
const fetching = ref(false)
const saving = ref(false)
const fetchError = ref('')
const form = reactive({
  id: '', protocol: 'openai', endpoint: '', apiKey: '', models: [] as string[], modelInput: '',
})

const step1Valid = computed(() =>
  /^[a-z0-9][a-z0-9_-]*$/.test(form.id)
  && /^https?:\/\//.test(form.endpoint)
  && !(sec.value?.profiles?.[form.id]))

function openWizard() {
  step.value = 1
  wizard.value = true
  fetchError.value = ''
  Object.assign(form, { id: '', protocol: props.section === 'llm' ? 'openai' : 'openai', endpoint: '', apiKey: '', models: [], modelInput: '' })
}

function choosePreset(p: Preset) {
  form.id = p.id
  form.protocol = p.protocol
  form.endpoint = p.endpoint
  form.models = [...(p.models || [])]
  step.value = 2
}

function addModel() {
  const m = form.modelInput.trim()
  if (!m) return
  if (!form.models.includes(m)) form.models.push(m)
  form.modelInput = ''
}

function removeModel(m: string) {
  form.models = form.models.filter(x => x !== m)
}

async function fetchModels() {
  fetching.value = true
  fetchError.value = ''
  try {
    const profile = {
      provider: form.protocol,
      endpoint: form.endpoint,
      chat_path: form.protocol === 'anthropic' ? '/v1/messages' : '/v1/chat/completions',
      api_key: form.apiKey,
      timeout: 30,
    }
    const r = await api.fetchModels(props.section, profile)
    if (r.ok && r.models?.length) {
      for (const m of r.models) if (!form.models.includes(m)) form.models.push(m)
      notify.ok(`已获取 ${r.models.length} 个模型`)
    } else {
      fetchError.value = r.error || '获取模型失败，可手动输入模型 ID'
    }
  } catch (e: any) {
    fetchError.value = e?.message || '获取模型失败，可手动输入模型 ID'
  } finally {
    fetching.value = false
  }
}

async function save() {
  if (!form.models.length) return
  saving.value = true
  try {
    const profile: Record<string, any> = {
      provider: form.protocol,
      endpoint: form.endpoint,
      model: form.models[0],
      models: [...form.models],
      chat_path: form.protocol === 'anthropic' ? '/v1/messages' : '/v1/chat/completions',
      timeout: 60,
    }
    if (props.section === 'asr') profile.language = 'zh'
    if (props.section === 'tts') { profile.format = 'wav'; profile.voice = '' }
    if (!sec.value.profiles) sec.value.profiles = {}
    sec.value.profiles[form.id] = profile
    sec.value.active = form.id
    if (form.apiKey) {
      await api.putSecret(`${props.section}.profiles.${form.id}`, form.apiKey)
    }
    await s.saveModule(props.section)
    await s.load()
    notify.ok(`供应商「${form.id}」已保存`)
    wizard.value = false
  } catch (e: any) {
    notify.err('保存供应商失败：' + (e?.message || e))
  } finally {
    saving.value = false
  }
}

async function activate(id: string) {
  if (sec.value.active === id) return
  if (!sec.value.profiles) sec.value.profiles = {}
  sec.value.active = id
  await s.saveModule(props.section)
  await s.load()
}

async function removeProvider(id: string) {
  delete sec.value.profiles[id]
  if (sec.value.active === id) sec.value.active = Object.keys(sec.value.profiles)[0] || ''
  await s.saveModule(props.section)
  await s.load()
  notify.ok(`已删除供应商「${id}」`)
}
</script>

<style scoped>
.mp-list { display: flex; flex-direction: column; gap: var(--sp-2); }
.mp-item {
  position: relative; display: grid; grid-template-columns: 1fr auto; gap: 2px var(--sp-3);
  text-align: left; padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  background: rgba(15, 23, 42, .5); color: var(--text-2); cursor: pointer;
}
.mp-item:hover, .mp-item.on { border-color: var(--brand-c2); background: rgba(103, 232, 249, .06); }
.mp-name { font-weight: 600; color: var(--text-1); font-size: var(--fs-sm); }
.mp-meta { font-size: var(--fs-2xs); color: var(--text-3); text-align: right; }
.mp-url { font-size: var(--fs-2xs); color: var(--text-3); font-family: var(--font-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mp-key { font-size: var(--fs-2xs); color: #f87171; text-align: right; }
.mp-key.set { color: #34d399; }
.mp-active { font-size: var(--fs-2xs); color: var(--brand-c2); }
.mp-del { position: absolute; right: var(--sp-2); bottom: var(--sp-1); color: var(--text-3); padding: 0 4px; }
.mp-del:hover { color: #f87171; }
.mp-form { display: flex; flex-direction: column; gap: var(--sp-3); }
.mp-presets { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
.mp-preset {
  display: flex; flex-direction: column; gap: 1px; padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  background: rgba(15, 23, 42, .5); color: var(--text-1); cursor: pointer;
}
.mp-preset span { font-size: var(--fs-2xs); color: var(--text-3); }
.mp-fetch { display: flex; align-items: center; gap: var(--sp-2); }
.mp-err { font-size: var(--fs-2xs); color: #f87171; }
.mp-models { display: flex; flex-wrap: wrap; gap: var(--sp-q6); }
.mp-model {
  display: inline-flex; align-items: center; gap: var(--sp-1);
  padding: 1px var(--sp-q10); border-radius: var(--r-full);
  background: rgba(103, 232, 249, .08); border: 1px solid rgba(103, 232, 249, .25);
  font-size: var(--fs-2xs); color: var(--brand-c2);
}
.mp-model-x { cursor: pointer; color: var(--text-3); }
.mp-model-x:hover { color: #f87171; }
.mp-addmodel { display: flex; gap: var(--sp-2); margin-top: var(--sp-2); }
.mp-actions { display: flex; justify-content: flex-end; gap: var(--sp-2); margin-top: var(--sp-2); }
</style>
