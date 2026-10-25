import { ref } from 'vue'
import { api } from '../../../api'
import { useConfig } from '../../../composables/useApi'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import type { EditableSnapshot } from '../../../types'
import { testPassed } from './detection'
import { status as voiceStatus, voiceAllReady } from '../../../composables/useVoiceModuleStatus'

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
 * 判断指定菜单项是否显示绿点。
 * 绿点语义（2026-10-11）：
 * - LLM / ASR / TTS：测过 → 以最近一次测试结果为准（通过=绿、失败=灰）；没测过 →
 *   回退「密钥已设置」。
 * - 语音：唤醒启用且至少配了一个唤醒词 → 绿（「开启且正常」）。
 * - 权限 / 高级设置：不设绿点（用户裁定）。
 * Check whether a menu item shows the green dot.
 * Semantics (2026-10-11): LLM/ASR/TTS — tested → last test result wins (pass = green,
 * fail = gray); untested → "API key set" fallback. Voice — wake enabled with at least
 * one wake word = green ("enabled and healthy"). Permissions / Advanced — no dot (user
 * ruling).
 *
 * @param id 菜单项 id。Menu item id.
 * @returns 是否显示绿点。Whether the dot is shown.
 */
export function menuDot(id: string): boolean {
  if (id === 'llm' || id === 'asr' || id === 'tts') {
    const tested = testPassed.value[id]
    if (tested !== undefined) return tested
    const s = (editable.value as any)?.[id]
    return !!s?.api_key_set?.[s.active]
  }
  if (id === 'voice') {
    // 语音聚合灯：四模块都就绪（VAD/KWS/ASR/TTS）才绿；能力状态由后端定义。
    // Voice aggregate dot: all four modules ready, as defined by the backend.
    const w = (editable.value as any)?.wake_word
    // 能力状态尚未拉取时退回旧判据（唤醒启用 + 有唤醒词），拉取后以四模块就绪为准。
    // Before capabilities load, fall back to wake enabled + keywords; after load, use
    // all four modules' readiness.
    const capsReady = voiceStatus.value ? voiceAllReady.value : true
    return !!w?.enabled && (w?.keywords?.length ?? 0) > 0 && capsReady
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
/** ASR 段可提交字段（显式挑字段，只读标记不回送）。Submittable ASR fields. */
function _asrBody(e: any): Record<string, any> {
  return {
    active: e.asr.active, profiles: e.asr.profiles, mode: e.asr.mode,
    local_model: e.asr.local_model, streaming: e.asr.streaming,
    provider: e.asr.provider, device: e.asr.device, num_threads: e.asr.num_threads,
    params: e.asr.params,
  }
}

export function moduleBody(id: string): Record<string, any> {
  const e = editable.value as any
  if (id === 'voice') return { wake_word: e.wake_word, vad: e.vad }
  if (id === 'advanced') {
    return {
      agent: e.agent,
      llm_client: e.llm_client,
      tools: e.tools,
      rag: e.rag,
      memory: e.memory,
      server: { host: e.server.host, port: e.server.port, open_browser: e.server.open_browser, cors_origins: e.server.cors_origins },
      mcp: e.mcp,
    }
  }
  if (id === 'models') {
    // 本地模型 / 硬件卡：四能力 + 流式 + 浏览器设备。ASR 显式挑字段，避免把只读的
    // local_model_present / api_key_set 回送（extra=forbid → 400）。
    // Local-models card: four capabilities + streaming + browser devices. ASR is built
    // explicitly so read-only fields never ride back (extra=forbid → 400).
    return {
      vad: e.vad,
      kws: e.kws,
      asr: {
        mode: e.asr.mode, local_model: e.asr.local_model, streaming: e.asr.streaming,
        provider: e.asr.provider, device: e.asr.device, num_threads: e.asr.num_threads,
        params: e.asr.params, active: e.asr.active, profiles: e.asr.profiles,
      },
      tts: {
        enabled: e.tts.enabled, active: e.tts.active, profiles: e.tts.profiles,
        mode: e.tts.mode, local_model: e.tts.local_model, provider: e.tts.provider,
        device: e.tts.device, num_threads: e.tts.num_threads, speaker: e.tts.speaker,
        speed: e.tts.speed, lang: e.tts.lang, params: e.tts.params,
      },
      streaming: e.streaming,
      hardware: e.hardware,
    }
  }
  if (id === 'tts') return {
    tts: {
      enabled: e.tts.enabled, active: e.tts.active, profiles: e.tts.profiles,
      mode: e.tts.mode, local_model: e.tts.local_model, provider: e.tts.provider,
      device: e.tts.device, num_threads: e.tts.num_threads, speaker: e.tts.speaker,
      speed: e.tts.speed, lang: e.tts.lang, params: e.tts.params,
    },
  }
  // 权限段不是 profile 形状，必须单独分支 —— 否则会落到下面的兜底分支，
  // PATCH 出 {active: undefined, profiles: undefined} 这样的垃圾数据。
  // The permissions section is not profile-shaped, so it needs its own branch; the
  // fall-through below would PATCH garbage like {active: undefined, profiles: undefined}.
  if (id === 'permissions') return { permissions: e.permissions }
  // ASR 段不是纯 profile 形状：转写模式（mode）与本地模型目录（local_model）也要带上 ——
  // 落到下面的兜底分支只会发 {active, profiles}，用户切换的模式会被**静默丢弃**（保存看似成功）。
  // ⚠️ 只读的 local_model_present 绝不回送（后端 extra="forbid" → 400）。
  // The ASR section is not plain profile-shaped: the transcription mode and the local
  // model dir must ride along, or the fall-through below would silently drop the user's
  // mode selection. The read-only local_model_present is never sent back.
  if (id === 'asr') return { asr: _asrBody(e) }
  // 识别 Tab 的统一保存：本地引擎（VAD/KWS/ASR）+ 云端 ASR profile 一次提交。
  // Unified recognition save: local engines plus the cloud ASR profile in one PATCH.
  if (id === 'recognition') {
    return { vad: e.vad, kws: e.kws, asr: _asrBody(e), streaming: e.streaming }
  }
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
