import { ref } from 'vue'
import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import type { ProfileConfig, ProviderPreset } from '../../../types'
import { editable, moduleBody } from './state'

/**
 * 厂商目录与 Profile 管理（LLM / ASR / TTS 三模块共用）。
 * Vendor catalog and Profile management (shared by the LLM / ASR / TTS modules).
 */

/** 厂商目录预设列表（按模块分组）。Vendor catalog presets (grouped by module). */
export const catalog = ref<Record<string, ProviderPreset[]> | null>(null)
/** 当前正在新增 Profile 的模块 key。Module key currently adding a Profile. */
export const addingSection = ref<string | null>(null)
/** 是否正在输入自定义 Profile 名称。Whether custom Profile name input is active. */
export const customAdding = ref<string | null>(null)
/** 自定义 Profile 名称。Custom Profile name. */
export const customName = ref('')

/**
 * 获取当前活跃的 Profile 配置。
 * Get the currently active Profile config.
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 当前 Profile。The active profile.
 */
export function activeProfile(s: any): ProfileConfig {
  return (editable.value as any)?.[s.key]?.profiles?.[(editable.value as any)[s.key].active] || {}
}

/**
 * 根据 Profile 的 vendor 字段查找对应的厂商预设。
 * Find the vendor preset matching the Profile's vendor field.
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 厂商预设或 null。The vendor preset, or null.
 */
export function vendorPreset(s: any): ProviderPreset | null {
  const prof = activeProfile(s)
  if (!prof.vendor || !catalog.value) return null
  return catalog.value[s.key]?.find((v) => v.id === prof.vendor) || null
}

/**
 * 获取指定模块的厂商预设列表。
 * Get the vendor preset list for a module.
 *
 * @param key 模块 key。Module key.
 * @returns 厂商预设列表。The vendor preset list.
 */
export function vendorList(key: string): ProviderPreset[] {
  return (catalog.value && catalog.value[key]) || []
}

/**
 * 合并 Profile 和厂商预设的模型列表（去重）。
 * Merge model lists from the Profile and its vendor preset (deduplicated).
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 去重后的模型列表。The deduplicated model list.
 */
export function modelOptions(s: any): string[] {
  const prof = activeProfile(s)
  const v = vendorPreset(s)
  return [...new Set([...(prof.models || []), ...(v?.models || [])])].filter(Boolean)
}

/**
 * 合并 Profile 和厂商预设的音色列表（去重）。
 * Merge voice lists from the Profile and its vendor preset (deduplicated).
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 去重后的音色列表。The deduplicated voice list.
 */
export function voiceOptions(s: any): string[] {
  const prof = activeProfile(s)
  const v = vendorPreset(s)
  return [...new Set([...(prof.voices || []), ...(v?.voices || [])])].filter(Boolean)
}

/**
 * 目录预设 → 可编辑 profile（与后端 core/providers.preset_to_profile 对齐）。
 * Convert a catalog preset to an editable profile (aligned with the backend's
 * core/providers.preset_to_profile).
 *
 * @param v 厂商预设。The vendor preset.
 * @returns 可编辑的 Profile 配置。The editable profile config.
 */
export function presetToProfile(v: ProviderPreset): ProfileConfig {
  const p: any = {
    provider: v.provider || 'openai',
    vendor: v.id,
    endpoint: v.endpoint,
    chat_path: v.chat_path || '/v1/chat/completions',
    models: [...v.models],
    model: v.defaults?.model || v.models[0] || '',
    api_key_env: v.api_key_env,
    compat: { ...v.compat },
  }
  if (v.models_path) p.models_path = v.models_path
  if (v.vision_models?.length) p.vision_model = v.vision_models[0]
  if (v.voices?.length) {
    p.voices = [...v.voices]
    p.voice = v.defaults?.voice || v.voices[0]
  }
  for (const [k, val] of Object.entries(v.defaults || {})) {
    if (p[k] === undefined) p[k] = val
  }
  return p
}

/**
 * 切换「新增 Profile」面板的展开/折叠。
 * Toggle the "Add Profile" panel expand/collapse.
 *
 * @param key 模块 key。Module key.
 */
export function toggleAdding(key: string) {
  addingSection.value = addingSection.value === key ? null : key
  customAdding.value = null
}

/**
 * 只持久化单个模块（新增/删除 Profile 用，静默不弹提示）。
 * Persist a single module only (for add/delete Profile, silently).
 *
 * @param key 模块 key。Module key.
 * @returns 是否保存成功。Whether the save succeeded.
 */
export async function persistSection(key: string): Promise<boolean> {
  if (!editable.value) return false
  try {
    const r = await api.patchConfig(moduleBody(key))
    return !!r.ok
  } catch {
    return false
  }
}

/**
 * 自定义空白 Profile：内联输入取名 → 建空 profile 并立即保存。
 * Custom blank Profile: inline name input, then created and saved immediately.
 *
 * @param key 模块 key。Module key.
 */
export async function confirmCustom(key: string) {
  const name = customName.value.trim() || 'custom'
  const profiles = (editable.value as any)[key].profiles
  if (profiles[name]) { notify.err(`Profile「${name}」已存在`); return }
  profiles[name] = { provider: 'openai', chat_path: '/v1/chat/completions', models: [] }
  ;(editable.value as any)[key].active = name
  customAdding.value = null
  customName.value = ''
  const ok = await persistSection(key)
  if (ok) notify.ok(`已添加并保存空白 Profile「${name}」，请填写 endpoint/模型 并设置 API Key`)
  else notify.err(`已添加 Profile「${name}」（保存失败，请检查后手动保存）`)
}

/**
 * 从厂商目录新增 Profile 并立即保存。
 * Add a Profile from the vendor catalog and save it immediately.
 *
 * @param key 模块 key。Module key.
 * @param v 厂商预设。The vendor preset.
 */
export async function addProfileFromVendor(key: string, v: ProviderPreset) {
  const profiles = (editable.value as any)[key].profiles
  let name = v.id
  let i = 2
  while (profiles[name]) name = `${v.id}-${i++}`
  profiles[name] = presetToProfile(v)
  ;(editable.value as any)[key].active = name
  addingSection.value = null
  const ok = await persistSection(key)
  if (ok) notify.ok(`已添加并保存 Profile「${name}」，请设置 API Key`)
  else notify.err(`已添加 Profile「${name}」（保存失败，请检查后手动保存）`)
}

/**
 * 删除指定 Profile（至少保留一个）。
 * Delete the specified Profile (at least one must remain).
 *
 * @param key 模块 key。Module key.
 */
export async function deleteProfile(key: string) {
  const s = (editable.value as any)[key]
  const names = Object.keys(s.profiles)
  if (names.length <= 1) { notify.err('至少保留一个 Profile'); return }
  const name = s.active
  if (!window.confirm(`删除 Profile「${name}」？`)) return
  delete s.profiles[name]
  const rest = Object.keys(s.profiles)
  if (!rest.includes(s.active)) s.active = rest[0]
  const ok = await persistSection(key)
  if (ok) notify.ok(`已删除 Profile「${name}」`)
  else notify.err(`已删除 Profile「${name}」（保存失败，请检查）`)
}

/**
 * 拉取当前 profile 的模型列表（openai/anthropic/gemini 均支持），写回 profile.models。
 * Fetch the model list for the current profile (openai/anthropic/gemini all
 * supported) and write it back to profile.models.
 *
 * @param s 服务模块定义。The service module definition.
 */
export async function fetchModelsFor(s: any) {
  const prof = activeProfile(s)
  const profile = { name: (editable.value as any)[s.key].active, ...prof }
  try {
    const r = await api.fetchModels(s.key, profile)
    if (r.ok) {
      prof.models = r.models
      if (r.models.length && (!prof.model || !r.models.includes(prof.model))) prof.model = r.models[0]
      notify.ok(`已获取 ${r.count} 个模型`)
    } else {
      notify.err('获取模型失败：' + (r.error || ''))
    }
  } catch (e) {
    notify.err('获取模型失败：' + formatError(e))
  }
}

/**
 * 从后端拉取厂商目录预设（失败不阻塞设置页）。
 * Fetch the vendor catalog from the backend (failure does not block the settings page).
 */
export async function loadCatalog() {
  try {
    const r = await api.getProviders()
    if (r.ok) catalog.value = r.catalog
  } catch { /* 目录拉取失败不阻塞设置页 / Catalog failure does not block the settings page */ }
}
