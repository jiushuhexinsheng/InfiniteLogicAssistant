import { ref } from 'vue'
import { api } from '../../../api'
import { useConfig } from '../../../composables/useApi'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import type { EditableSnapshot } from '../../../types'

/**
 * 设置页的核心状态与配置读写。
 * Core settings-page state and config load/save.
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
export const app = useConfig()
/** 可编辑配置快照（从后端 /api/config/full 获取）。Editable config snapshot (from backend /api/config/full). */
export const editable = ref<EditableSnapshot | null>(null)
/** 保存中状态标志。Saving state flag. */
export const saving = ref(false)
/** 左侧菜单当前选中项。Currently selected left menu item. */
export const activeMenu = ref('llm')

/**
 * 获取指定模块的可编辑配置对象。
 * Get the editable config object for a module.
 *
 * @param key 模块 key。Module key.
 * @returns 该模块的配置对象。The module's config object.
 */
export function sec(key: string): any {
  return (editable.value as any)?.[key]
}

/**
 * 语音模块顶层对象（wake_word / vad 直接挂在 editable 根）。
 * Voice module top-level object (wake_word / vad sit at the editable root).
 *
 * @returns 可编辑快照根对象。The editable snapshot root.
 */
export function ed(): any {
  return editable.value
}

/**
 * 判断指定菜单项是否显示绿点（密钥已设置）。
 * Check whether a menu item shows the "key set" dot.
 *
 * @param id 菜单项 id。Menu item id.
 * @returns 是否显示绿点。Whether the dot is shown.
 */
export function menuDot(id: string): boolean {
  if (id === 'llm' || id === 'asr' || id === 'tts') {
    const s = (editable.value as any)?.[id]
    return !!s?.api_key_set?.[s.active]
  }
  return false
}

/**
 * 按模块产出 PATCH body（service: 只该 section；voice: 唤醒+VAD；advanced: 全部高级段）。
 * Build the PATCH body by module (service: that section only; voice: wake+VAD;
 * advanced: all advanced sections).
 *
 * @param id 模块 key。Module key.
 * @returns PATCH 请求体。The PATCH request body.
 */
export function moduleBody(id: string): Record<string, any> {
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
  // 权限段不是 profile 形状，必须单独分支 —— 否则会落到下面的兜底分支，
  // PATCH 出 {active: undefined, profiles: undefined} 这样的垃圾数据。
  // The permissions section is not profile-shaped, so it needs its own branch; the
  // fall-through below would PATCH garbage like {active: undefined, profiles: undefined}.
  if (id === 'permissions') return { permissions: e.permissions }
  return { [id]: { active: e[id].active, profiles: e[id].profiles } }
}

/**
 * 从后端加载完整可编辑配置。
 * Load the full editable config from the backend.
 */
export async function load() {
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
 * 保存单个模块的配置到后端。
 * Save a single module's config to the backend.
 *
 * @param id 模块 key。Module key.
 */
export async function saveModule(id: string) {
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
