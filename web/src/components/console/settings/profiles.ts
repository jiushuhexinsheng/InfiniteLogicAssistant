import { ref } from 'vue'
import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import type { ProfileConfig } from '../../../types'
import { editable, moduleBody } from './state'

/**
 * Profile 管理（LLM / ASR / TTS 三模块共用）—— 全部自填，无厂商目录
 * （2026-10-11 目录退役：endpoint/模型/协议/密钥由用户手填或「获取模型」拉取）。
 *
 * Profile management (shared by the LLM / ASR / TTS modules) — entirely self-filled,
 * no vendor catalogue (retired 2026-10-11: endpoint/model/protocol/key are filled in
 * by hand or pulled via "fetch models").
 */

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
 * 当前 Profile 自己维护的模型列表（无目录合并；「获取模型」按钮填充）。
 * The active profile's own model list (no catalogue merge; the "fetch models" button fills it).
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 模型列表。The model list.
 */
export function modelOptions(s: any): string[] {
  return [...new Set(activeProfile(s).models || [])].filter(Boolean)
}

/**
 * 当前 Profile 自己维护的音色列表（无目录合并）。
 * The active profile's own voice list (no catalogue merge).
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 音色列表。The voice list.
 */
export function voiceOptions(s: any): string[] {
  return [...new Set(activeProfile(s).voices || [])].filter(Boolean)
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
 * 自定义空白 Profile：内联输入取名 → 建空 profile 并立即保存（唯一新增路径）。
 * Custom blank Profile: inline name input, then created and saved immediately (the
 * only way to add a Profile).
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

// ─── 高级兼容开关（目录退役后的自填闭环：网关特殊补丁不再靠预设预填） ───
// Advanced gateway compatibility toggles (the self-fill loop after the catalogue
// retired: gateway-specific patches are no longer pre-filled by presets).

/** 常用兼容开关快捷项（点击即写入当前 profile 的 compat）。Common compat shortcuts. */
export const COMPAT_SHORTCUTS: { label: string; key: string; value: string }[] = [
  { label: 'api-key 认证头', key: 'auth_header', value: 'api-key' },
  { label: '音频 data-URL', key: 'audio_data_url', value: 'true' },
  { label: '附带语言', key: 'send_language', value: 'true' },
  { label: '拒绝文本部件', key: 'no_text_parts', value: 'true' },
  { label: '用量统计', key: 'stream_options', value: 'true' },
  { label: 'max_tokens 改名', key: 'max_tokens_field', value: 'max_completion_tokens' },
]

/** 当前 profile 的 compat 对象（不存在先初始化）。The active profile's compat object
 *  (initialized when missing). */
function mutableCompat(s: any): Record<string, unknown> {
  const prof = activeProfile(s) as any
  if (!prof) return {}
  if (!prof.compat || typeof prof.compat !== 'object') prof.compat = {}
  return prof.compat
}

/** 读取兼容键值（展示为字符串行）。Read compat entries as display string rows. */
export function compatEntries(s: any): [string, string][] {
  return Object.entries(mutableCompat(s)).map(([k, v]) => [k, typeof v === 'string' ? v : String(v)])
}

/** 智能解析输入值：true/false → 布尔，纯数字 → number，其余原样字符串。
 *  Smart-parse an input: true/false → boolean, pure digits → number, else the raw string. */
export function parseCompatValue(raw: string): unknown {
  const t = raw.trim()
  if (t === 'true') return true
  if (t === 'false') return false
  if (t !== '' && !Number.isNaN(Number(t))) return Number(t)
  return raw
}

/** 写入一个兼容键（改键名 = 删旧建新）。Write a compat key (renaming = delete + create). */
export function setCompat(s: any, key: string, raw: string, oldKey?: string) {
  const k = key.trim()
  if (!k) return
  const compat = mutableCompat(s)
  if (oldKey && oldKey !== k) delete compat[oldKey]
  compat[k] = parseCompatValue(raw)
}

/** 删除一个兼容键。Delete a compat key. */
export function removeCompat(s: any, key: string) {
  delete mutableCompat(s)[key]
}

/** 快捷项开关：已有同键则移除，否则按快捷值写入（一次点击可逆）。
 *  Shortcut toggle: removes an existing key, otherwise writes the shortcut value
 *  (one click, reversible). */


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
