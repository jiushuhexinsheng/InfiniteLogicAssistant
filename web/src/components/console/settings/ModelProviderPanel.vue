<template>
  <!-- 模型供应商：列表面板 + 新增/编辑向导（大模型 / ASR / TTS 共用）。
       Model providers: list + add/edit wizard, shared by LLM / ASR / TTS. -->
  <SettingsCard title="模型供应商" title-en="Model Providers">
    <ProviderList
      :providers="providers"
      @add="openWizard(null)"
      @edit="openWizard"
      @remove="removeProvider"
      @activate="activate"
    />
    <ProviderWizard
      v-model="wizardOpen"
      :section="section"
      :editing-id="editingId"
      :profiles="profiles"
      :key-set="editingKeySet"
      @saved="afterSaved"
      @close="editingId = null"
    />
  </SettingsCard>
</template>

<script setup lang="ts">
/**
 * 供应商面板：把 editable 快照转成列表摘要，负责删除（含密钥清理）与设为当前；
 * 新增/编辑的字段编辑全部在 ProviderWizard 内完成。
 *
 * Provider panel: maps the editable snapshot to list summaries, owns deletion
 * (including secret cleanup) and activation; field editing lives in ProviderWizard.
 */
import { computed, ref } from 'vue'
import SettingsCard from './SettingsCard.vue'
import ProviderList from './ProviderList.vue'
import ProviderWizard from './ProviderWizard.vue'
import type { ProviderSummary } from './providerTypes'
import { persistSection } from './profiles'
import { useSettings } from './useSettings'
import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import type { ProviderSection } from './providerPresets'

const props = defineProps<{ section: ProviderSection }>()
const s = useSettings()

const wizardOpen = ref(false)
const editingId = ref<string | null>(null)

/** 当前 section 的实际配置。The section's editable config. */
function sec(): any {
  return s.sec(props.section) as any
}

/** profiles 映射。Profiles mapping. */
const profiles = computed<Record<string, any>>(() => sec()?.profiles || {})

/** 模型数 = models ∪ model。Model count = models ∪ model. */
function modelCount(profile: any): number {
  const out: string[] = []
  for (const raw of [profile?.model || '', ...(profile?.models || [])]) {
    const value = String(raw || '').trim()
    if (value && !out.includes(value)) out.push(value)
  }
  return out.length
}

/** 列表摘要（active 空串按运行时规则解析为第一个 profile）。List summaries. */
const providers = computed<ProviderSummary[]>(() => {
  const config = sec()
  const activeId = config?.active && config.profiles?.[config.active]
    ? config.active
    : (Object.keys(config?.profiles || {})[0] || '')
  return Object.entries(config?.profiles || {}).map(([id, profile]: [string, any]) => ({
    id,
    name: profile.name || id,
    protocol: profile.provider || 'openai',
    endpoint: profile.endpoint || '',
    keySet: !!config?.api_key_set?.[id],
    active: id === activeId,
    modelCount: modelCount(profile),
  }))
})

/** 正在编辑的供应商是否已有密钥。Whether the edited provider already has a key. */
const editingKeySet = computed(() => !!sec()?.api_key_set?.[editingId.value || ''])

/** 打开向导；id 为空 = 新增。Open the wizard; null id = add. */
function openWizard(id: string | null): void {
  editingId.value = id
  wizardOpen.value = true
}

/** 保存后刷新快照。Refresh the snapshot after save. */
async function afterSaved(): Promise<void> {
  await s.load()
}

/** 删除供应商：先删 profile，再清 secrets；清理失败只提示不回滚。Delete provider. */
async function removeProvider(id: string): Promise<void> {
  const config = sec()
  delete config.profiles[id]
  if (config.active === id) config.active = Object.keys(config.profiles)[0] || ''
  const ok = await persistSection(props.section)
  if (!ok) {
    notify.err('删除供应商失败')
    return
  }
  try {
    await api.putSecret(`${props.section}.profiles.${id}`, '')
  } catch {
    notify.err(`供应商「${id}」已删除，但密钥清理失败`)
  }
  await s.load()
  notify.ok(`已删除供应商「${id}」`)
}

/** 设为当前（全局）。Set as the global active provider. */
async function activate(id: string): Promise<void> {
  const config = sec()
  if (config.active === id) return
  config.active = id
  const ok = await persistSection(props.section)
  if (!ok) {
    notify.err('切换供应商失败')
    return
  }
  await s.load()
  notify.ok(`已将「${id}」设为当前供应商`)
}
</script>
