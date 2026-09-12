import { ref } from 'vue'
import { api } from '../../../api'
import { useConfig } from '../../../composables/useApi'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import type {
  ConnectivityResult, DetectionIssue, EditableSnapshot, ProfileConfig, ProviderPreset,
} from '../../../types'

/**
 * 设置页状态单例 + API 操作。
 * Settings-page state singleton + API operations.
 *
 * state 定义在模块顶层（与 useConsole.ts 的 activeTab、assistant/store.ts 同模式），
 * 因此各子组件无需逐层传 props 即可共享同一份配置快照。副作用：state 跨
 * ConsoleSettings 挂载/卸载存活，故 ConsoleSettings 必须保留 onMounted 时重新 load()。
 *
 * State lives at module top level (same pattern as useConsole.ts's activeTab and
 * assistant/store.ts), so sub-components share one config snapshot without prop
 * drilling. Side effect: state survives ConsoleSettings mount/unmount, so
 * ConsoleSettings MUST keep its onMounted re-load().
 */

/** 全局配置缓存（tts_available、当前 profile 等）。Global config cache (tts_available, current profile, etc.). */
const app = useConfig()
/** 可编辑配置快照（从后端 /api/config/full 获取）。Editable config snapshot (from backend /api/config/full). */
const editable = ref<EditableSnapshot | null>(null)
/** 保存中状态标志。Saving state flag. */
const saving = ref(false)
/** 检测中状态标志。Detection in progress flag. */
const detecting = ref(false)
/** 连通性检测结果（按服务名索引）。Connectivity results (indexed by service name). */
const connResults = ref<Record<string, ConnectivityResult>>({})
/** 配置校验问题列表。Config validation issues. */
const issues = ref<DetectionIssue[]>([])
/** 厂商目录预设列表（按模块分组）。Vendor catalog presets (grouped by module). */
const catalog = ref<Record<string, ProviderPreset[]> | null>(null)
/** 当前正在新增 Profile 的模块 key。Module key currently adding a Profile. */
const addingSection = ref<string | null>(null)
/** 是否正在输入自定义 Profile 名称。Whether custom Profile name input is active. */
const customAdding = ref<string | null>(null)
/** 自定义 Profile 名称。Custom Profile name. */
const customName = ref('')
/** 左侧菜单当前选中项。Currently selected left menu item. */
const activeMenu = ref('llm')
/** 密钥弹出框状态（section / profile / value）。API Key modal state. */
const keyModal = ref<{ section: string; profile: string; value: string } | null>(null)
/** 是否显示明文密钥。Whether to show the key in plain text. */
const showKey = ref(false)

/**
 * 获取指定模块的可编辑配置对象。
 * Get the editable config object for a module.
 *
 * @param key 模块 key。Module key.
 * @returns 该模块的配置对象。The module's config object.
 */
function sec(key: string): any {
  return (editable.value as any)?.[key]
}

/**
 * 语音模块顶层对象（wake_word / vad 直接挂在 editable 根）。
 * Voice module top-level object (wake_word / vad sit at the editable root).
 *
 * @returns 可编辑快照根对象。The editable snapshot root.
 */
function ed(): any {
  return editable.value
}

/**
 * 判断指定菜单项是否显示绿点（密钥已设置）。
 * Check whether a menu item shows the "key set" dot.
 *
 * @param id 菜单项 id。Menu item id.
 * @returns 是否显示绿点。Whether the dot is shown.
 */
function menuDot(id: string): boolean {
  if (id === 'llm' || id === 'asr' || id === 'tts') {
    const s = (editable.value as any)?.[id]
    return !!s?.api_key_set?.[s.active]
  }
  return false
}

/**
 * 获取当前活跃的 Profile 配置。
 * Get the currently active Profile config.
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 当前 Profile。The active profile.
 */
function activeProfile(s: any): ProfileConfig {
  return (editable.value as any)?.[s.key]?.profiles?.[(editable.value as any)[s.key].active] || {}
}

/**
 * 根据 Profile 的 vendor 字段查找对应的厂商预设。
 * Find the vendor preset matching the Profile's vendor field.
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 厂商预设或 null。The vendor preset, or null.
 */
function vendorPreset(s: any): ProviderPreset | null {
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
function vendorList(key: string): ProviderPreset[] {
  return (catalog.value && catalog.value[key]) || []
}

/**
 * 合并 Profile 和厂商预设的模型列表（去重）。
 * Merge model lists from the Profile and its vendor preset (deduplicated).
 *
 * @param s 服务模块定义。The service module definition.
 * @returns 去重后的模型列表。The deduplicated model list.
 */
function modelOptions(s: any): string[] {
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
function voiceOptions(s: any): string[] {
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
function presetToProfile(v: ProviderPreset): ProfileConfig {
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
function toggleAdding(key: string) {
  addingSection.value = addingSection.value === key ? null : key
  customAdding.value = null
}

/**
 * 按模块产出 PATCH body（service: 只该 section；voice: 唤醒+VAD；advanced: 全部高级段）。
 * Build the PATCH body by module (service: that section only; voice: wake+VAD;
 * advanced: all advanced sections).
 *
 * @param id 模块 key。Module key.
 * @returns PATCH 请求体。The PATCH request body.
 */
function moduleBody(id: string): Record<string, any> {
  const e = editable.value as any
  if (id === 'voice') return { wake_word: e.wake_word, vad: e.vad }
  if (id === 'advanced') {
    return {
      agent: e.agent,
      llm_client: e.llm_client,
      tools: e.tools,
      rag: e.rag,
      server: { host: e.server.host, port: e.server.port, open_browser: e.server.open_browser, cors_origins: e.server.cors_origins },
      mcp: e.mcp,
    }
  }
  if (id === 'tts') return { tts: { enabled: e.tts.enabled, active: e.tts.active, profiles: e.tts.profiles } }
  return { [id]: { active: e[id].active, profiles: e[id].profiles } }
}

/**
 * 只持久化单个模块（新增/删除 Profile 用，静默不弹提示）。
 * Persist a single module only (for add/delete Profile, silently).
 *
 * @param key 模块 key。Module key.
 * @returns 是否保存成功。Whether the save succeeded.
 */
async function persistSection(key: string): Promise<boolean> {
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
async function confirmCustom(key: string) {
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
async function addProfileFromVendor(key: string, v: ProviderPreset) {
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
async function deleteProfile(key: string) {
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
async function fetchModelsFor(s: any) {
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
 * 保存单个模块的配置到后端。
 * Save a single module's config to the backend.
 *
 * @param id 模块 key。Module key.
 */
async function saveModule(id: string) {
  if (!editable.value) return
  saving.value = true
  try {
    const r = await api.patchConfig(moduleBody(id))
    if (r.ok) {
      notify.ok(r.restart_required ? '已保存（部分设置重启后生效）' : '已保存（已即时生效）')
      if (r.restart_required) notify.warn('服务器绑定 / MCP 已变更，重启服务后生效')
      // 刷新全局 /api/config 缓存，让 tts_available / 当前 profile 等即时更新（无需刷新页面）
      // Refresh the global /api/config cache so tts_available / the current profile update immediately.
      app.refreshConfig()
    } else {
      notify.err('保存失败：' + (r.error || ''))
    }
  } catch (e) {
    notify.err('保存失败：' + formatError(e))
  } finally {
    saving.value = false
  }
}

/**
 * 从后端加载完整可编辑配置。
 * Load the full editable config from the backend.
 */
async function load() {
  try {
    const r = await api.getConfigFull()
    if (r.ok && r.editable) {
      editable.value = r.editable
      // 若当前 active profile 不在 profiles（可能被清），回退到第一个
      // If the active profile is missing from profiles, fall back to the first one.
      for (const key of ['llm', 'asr', 'tts'] as const) {
        const s: any = r.editable[key]
        if (s && !s.profiles[s.active] && Object.keys(s.profiles).length) {
          s.active = Object.keys(s.profiles)[0]
        }
      }
    } else {
      notify.err('加载配置失败')
    }
  } catch (e) {
    notify.err('加载配置失败：' + formatError(e))
  }
}

/**
 * 检测全部服务连通性。
 * Test connectivity for all services.
 */
async function detectAll() {
  detecting.value = true
  issues.value = []
  try {
    const r = await api.getDetection()
    if (r.ok && r.report) {
      connResults.value = Object.fromEntries(r.report.connectivity.map((c) => [c.name, c]))
      issues.value = r.report.config.issues
    } else {
      notify.err('检测失败：' + ((r as any)?.error || ''))
    }
  } catch (e) {
    notify.err('检测失败：' + formatError(e))
  } finally {
    detecting.value = false
  }
}

/**
 * 检测单个服务连通性。
 * Test connectivity for a single service.
 *
 * @param name 服务名（LLM / ASR / TTS）。Service name (LLM / ASR / TTS).
 */
async function detectOne(name: string) {
  detecting.value = true
  try {
    const r = await api.getDetection()
    if (r.ok) {
      const c = r.report.connectivity.find((x) => x.name === name)
      if (c) connResults.value = { ...connResults.value, [name]: c }
    }
  } catch {
    /* 静默：单服务检测失败不影响整体显示 / Silent: a single-service failure does not affect the overall display */
  } finally {
    detecting.value = false
  }
}

/**
 * 打开密钥设置弹窗。
 * Open the API Key settings modal.
 *
 * @param section 模块 key。Module key.
 * @param profile Profile 名。Profile name.
 */
function openKeyModal(section: string, profile: string) {
  showKey.value = false
  keyModal.value = { section, profile, value: '' }
}

/**
 * 获取当前密钥对应的环境变量名（提示用户可通过 env 配置）。
 * Get the env var name for the current key (hints that env config is available).
 *
 * @returns 环境变量名，无则空串。The env var name, or an empty string.
 */
function keyEnvHint(): string {
  const m = keyModal.value
  if (!m) return ''
  return (editable.value as any)?.[m.section]?.profiles?.[m.profile]?.api_key_env || ''
}

/**
 * 确认保存 API Key（通过 PUT secret 接口）。
 * Confirm and save the API Key (via the PUT secret endpoint).
 */
async function confirmKey() {
  const m = keyModal.value
  if (!m) return
  const path = `${m.section}.profiles.${m.profile}`
  const label = `${m.section} · ${m.profile}`
  try {
    const r = await api.putSecret(path, m.value)
    if (r.ok) {
      if (r.set) notify.ok(`已设置 ${label} 密钥（即时生效）`)
      else notify.ok(`已清除 ${label} 密钥`)
      const s = (editable.value as any)?.[m.section]
      if (s?.api_key_set) s.api_key_set[m.profile] = r.set
      keyModal.value = null
    } else {
      notify.err('设置密钥失败：' + (r.error || ''))
    }
  } catch (e) {
    notify.err('设置密钥失败：' + formatError(e))
  }
}

/**
 * 清除当前 API Key（value 置空后调用 confirmKey）。
 * Clear the current API Key (empties the value, then calls confirmKey).
 */
async function clearKey() {
  const m = keyModal.value
  if (!m) return
  m.value = ''
  await confirmKey()
}

/**
 * 从后端拉取厂商目录预设（失败不阻塞设置页）。
 * Fetch the vendor catalog from the backend (failure does not block the settings page).
 */
async function loadCatalog() {
  try {
    const r = await api.getProviders()
    if (r.ok) catalog.value = r.catalog
  } catch { /* 目录拉取失败不阻塞设置页 / Catalog failure does not block the settings page */ }
}

/**
 * 设置页状态与操作入口（模块级单例）。
 * Settings-page state and operations entry point (module-level singleton).
 *
 * @returns 状态引用与操作函数。State refs and operation functions.
 */
export function useSettings() {
  return {
    app, editable, saving, detecting, connResults, issues, catalog,
    addingSection, customAdding, customName, activeMenu, keyModal, showKey,
    sec, ed, menuDot, activeProfile, vendorPreset, vendorList, modelOptions, voiceOptions,
    presetToProfile, toggleAdding, confirmCustom, addProfileFromVendor, deleteProfile,
    fetchModelsFor, saveModule, load, detectAll, detectOne,
    openKeyModal, keyEnvHint, confirmKey, clearKey, loadCatalog,
  }
}
