/**
 * 本地模型目录与硬件的共享状态（模块级单例，与 useSettings / state.ts 同模式）。
 *
 * 原 LocalModelsCard.vue 把「模型扫描 + schema 拉取 + 引擎自检 + 设备枚举 + 一键本地」
 * 全塞在一个组件里（610 行 / 22 个函数）。本 composable 收走全部数据与动作，组件只负责
 * 分段落渲染：识别 / 合成 / 流式 / 硬件 / 状态条各自一个 SFC。
 *
 * Shared state for the local-model catalog and hardware (module-level singleton, same
 * pattern as useSettings / state.ts). The former LocalModelsCard.vue carried model
 * scanning, schema fetching, engine self-tests, device enumeration and one-click-local in
 * one 610-line component; this composable owns all data and actions, while per-section
 * SFCs own rendering.
 */
import { computed, ref } from 'vue'

import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import { ttsSettings, saveTts } from '../../../composables/assistant/useTts'
import { refreshVoiceStatus } from '../../../composables/useVoiceModuleStatus'
import type { SchemaField } from './SchemaForm.vue'
import { useSettings } from './useSettings'

/** 四类本地模型能力。The four local-model capabilities. */
export type ModelKind = 'vad' | 'kws' | 'asr' | 'tts'
/** 卡片在语音页中的段落（一个组件按 Tab 复用）。Card sections reused per tab. */
export type LocalModelsScope = 'all' | 'overview' | 'recognition' | 'tts' | 'hardware' | 'advanced'
/** 状态标签色调。Status chip tone. */
export type StatusTone = 'ok' | 'err' | 'info' | 'neutral'
/** 一条能力状态行。One capability status row. */
export interface StatusRow { kind: string; text: string; tone: StatusTone }

/** 模型切换时按 modelId 保存/恢复模型专属参数（通用参数 provider/线程不随模型走）。
 *  Save/restore model-specific params by modelId; common provider/threads stay shared. */
const MODEL_KEYS: Record<ModelKind, string> = {
  vad: 'model', kws: 'model_dir', asr: 'local_model', tts: 'local_model',
}

// ── 模块级状态 / Module-level state ──
/** 已安装模型（按能力）。Installed models by capability. */
const models = ref<Record<string, any[]>>({})
/** 后端参数 schema（按能力）。Parameter schema by capability. */
const schemas = ref<Record<string, SchemaField[]>>({})
/** 引擎自检结果（按能力）。Engine self-test results. */
const engineTests = ref<Record<string, any>>({})
const testing = ref('')
/** 硬件快照。Hardware snapshot. */
const hw = ref<any>(null)
/** 四能力状态快照（后端 /api/voice/capabilities）。Four-capability status snapshot. */
const caps = ref<any>(null)
/** 浏览器输入/输出设备。Browser input/output devices. */
const devices = ref<MediaDeviceInfo[]>([])
const loading = ref(false)

/** 数值输入：空串保留，其余转 number。Numeric input helper. */
export function toNum(v: string): number | '' {
  return v === '' ? '' : Number(v)
}

/**
 * 本地模型目录与硬件的状态与动作。
 * Local-model catalog and hardware state and actions.
 *
 * @returns 共享状态引用与操作函数。Shared state refs and operations.
 */
export function useLocalModels() {
  const s = useSettings()

  /** 可用 provider（含 cpu）。Available providers (cpu included). */
  const providers = computed<string[]>(() => {
    const list = (hw.value?.providers || []) as string[]
    if (!list.length) return ['cpu']
    return list.includes('cpu') ? list : ['cpu', ...list]
  })

  /** 当前唤醒词（KWS 区展示）。Current wake words. */
  const currentWakeWords = computed(() =>
    (s.ed()?.wake_word?.keywords || []).filter(Boolean).join(' / '))

  /** 当前段落可自检的引擎：只在对应模式为本地时出现。Locally testable engines. */
  function testKindsFor(scope: LocalModelsScope): string[] {
    const e = s.ed()
    if (!e) return []
    if (scope === 'tts') return e.tts.mode === 'local' ? ['tts'] : []
    if (scope === 'recognition') {
      const kinds: string[] = []
      if (e.vad.mode === 'local') kinds.push('vad')
      if (e.kws.mode === 'local') kinds.push('kws')
      if (e.asr.mode === 'local' || e.asr.mode === 'hybrid') kinds.push('asr')
      return kinds
    }
    return ['vad', 'kws', 'asr']
  }

  /** 某能力的状态文案。Status text for one capability. */
  function capRow(label: string, cap: any, mode: string): StatusRow {
    if (!cap) return { kind: label, text: `${label} —`, tone: 'neutral' }
    if (mode === 'off') return { kind: label, text: `${label} 已关闭`, tone: 'neutral' }
    if (mode === 'cloud' || mode === 'api') {
      return { kind: label, text: `${label} API`, tone: 'info' }
    }
    return cap.present
      ? { kind: label, text: `${label} 本地 ✓`, tone: 'ok' }
      : { kind: label, text: `${label} 本地 · 模型缺失`, tone: 'err' }
  }

  /** 四能力状态行；识别页只给前三行，合成页只给 TTS。Live status rows per scope. */
  function statusRowsFor(scope: LocalModelsScope): StatusRow[] {
    const c = caps.value
    const e = s.ed()
    if (!c || !e) return []
    const ttsRow = capRow('TTS', c.tts, e.tts.mode)
    if (e.tts.mode === 'local' && ttsSettings.value.engine !== 'local') {
      ttsRow.text += ' · 播放：浏览器'
    }
    const rows = [
      capRow('VAD', c.vad, e.vad.mode),
      capRow('KWS', c.kws, e.kws.mode),
      capRow('ASR', c.asr, e.asr.mode),
      ttsRow,
    ]
    if (scope === 'recognition') return rows.slice(0, 3)
    if (scope === 'tts') return [ttsRow]
    return rows
  }

  /** 过滤 schema 中的 provider 选项（只保留当前构建真实支持的），并标注推荐后端。 */
  function schemaFor(kind: ModelKind): SchemaField[] {
    return (schemas.value[kind] || []).map((f) => {
      if (f.key !== 'provider' || !f.options) return f
      const ok = f.options.filter(o => providers.value.includes(String(o.value)))
      const rec = providers.value.includes('cuda') ? 'cuda'
        : providers.value.includes('coreml') ? 'coreml' : 'cpu'
      return {
        ...f,
        options: ok.length ? ok : f.options,
        hint: { zh: `推荐 ${rec.toUpperCase()}`, en: `Recommended: ${rec.toUpperCase()}` },
      }
    })
  }

  /** 模型下拉选项（value = 相对项目根路径）。Model options (value = root-relative path). */
  function modelOptions(kind: ModelKind) {
    return (models.value[kind] || []).map((m) => ({
      value: m.path,
      label: `${m.name}${m.valid ? '' : '（缺文件）'}`,
    }))
  }

  /** 缺失文件提示。Missing-files hint. */
  function missingHint(kind: ModelKind, path: string): string {
    const m = (models.value[kind] || []).find((x) => x.path === path)
    if (!m) return path ? '目录里没有这个模型，点「刷新模型」重新扫描' : ''
    if (m.valid) return ''
    return `缺文件：${(m.missing || []).join('、')}`
  }

  /** 切换模型：先按新模型家族拉 schema，再恢复该模型上次的参数。Switch model. */
  function switchModel(kind: ModelKind, next: string) {
    const e = s.ed()
    if (!e) return
    const key = MODEL_KEYS[kind]
    const old = String(e[kind]?.[key] || '')
    if (old === next) return
    const fields = (schemas.value[kind] || []).filter(f => (f.group || 'model') === 'model')
    if (!e[kind].params) e[kind].params = {}
    if (old) {
      const saved: Record<string, unknown> = {}
      for (const f of fields) saved[f.key] = e[kind][f.key]
      e[kind].params[old] = saved
    }
    // 先按新模型的家族拉 schema（字段/默认值可能不同），再恢复参数。
    // Fetch the new model's schema first (fields/defaults may differ), then restore params.
    void api.getSchema(kind as any, next).then((r) => {
      if (r?.ok) {
        schemas.value[kind] = r.params
        const fresh = r.params.filter((f: SchemaField) => (f.group || 'model') === 'model')
        const saved = e[kind].params?.[next]
        for (const f of fresh) {
          if (saved && Object.prototype.hasOwnProperty.call(saved, f.key)) {
            e[kind][f.key] = saved[f.key]
          } else if (f.default !== undefined) {
            e[kind][f.key] = f.default
          }
        }
      }
    })
    e[kind][key] = next
    engineTests.value = { ...engineTests.value, [kind]: undefined }
  }

  /** 加载并实际跑一次引擎；结果显示在卡片内。Load and exercise one engine. */
  async function testEngine(kind: ModelKind) {
    testing.value = kind
    try {
      const r = await api.testEngine(kind)
      engineTests.value = { ...engineTests.value, [kind]: r }
      // 自检结果写进后端 _HEALTH 缓存，刷新能力状态让链路条/状态灯即时反映。
      // The self-test writes into the backend _HEALTH cache; refresh so the chain/dots update.
      void refreshVoiceStatus()
      if (r.ok) notify.ok(`${kind.toUpperCase()} 自检通过（${r.latency_ms ?? '?'}ms）`)
      else notify.err(`${kind.toUpperCase()} 自检失败：${r.error || '未知错误'}`)
    } catch (e: any) {
      engineTests.value = { ...engineTests.value, [kind]: { ok: false, error: e?.message || String(e) } }
      notify.err(`${kind.toUpperCase()} 自检失败：${e?.message || e}`)
    } finally {
      testing.value = ''
    }
  }

  /** 当前选中模型无效时，自动改用该能力下第一个有效模型（只改表单，不自动保存）。 */
  function ensureSelection(kinds: ModelKind[] = ['vad', 'kws', 'asr', 'tts']) {
    const e = s.ed()
    if (!e) return
    const fix = (kind: ModelKind, current: string, set: (v: string) => void) => {
      const list = models.value[kind] || []
      if (list.some((m) => m.valid && m.path === current)) return
      const first = list.find((m) => m.valid)
      if (first) set(first.path)
    }
    if (kinds.includes('vad')) fix('vad', e.vad.model, (v) => { e.vad.model = v })
    if (kinds.includes('kws')) fix('kws', e.kws.model_dir, (v) => { e.kws.model_dir = v })
    if (kinds.includes('asr')) fix('asr', e.asr.local_model, (v) => { e.asr.local_model = v })
    if (kinds.includes('tts')) fix('tts', e.tts.local_model, (v) => { e.tts.local_model = v })
  }

  /** 一键本地：按当前 Tab 只切换本页负责的能力，绝不越界改 TTS。 */
  function oneClickLocal(scope: LocalModelsScope) {
    const e = s.ed()
    if (!e) return
    const valid = (kind: ModelKind) => (models.value[kind] || []).filter((m) => m.valid)

    if (scope === 'tts') {
      const ttsReady = (models.value.tts || []).some(
        (m) => m.valid && m.path === e.tts.local_model,
      )
      if (!ttsReady) {
        notify.err('没有可用的本地 TTS 模型，请先下载或刷新模型')
        return
      }
      ensureSelection(['tts'])
      e.tts.mode = 'local'
      ttsSettings.value.engine = 'local'
      saveTts()
      notify.ok('已切换为本地 TTS（保存中）')
      void s.saveModule('tts')
      return
    }

    if (!valid('vad').length) {
      notify.err('没有可用的本地 VAD 模型，请先下载或刷新模型')
      return
    }
    if (!valid('asr').length) {
      notify.err('没有可用的本地 ASR 模型，请先下载或刷新模型')
      return
    }
    ensureSelection(['vad', 'kws', 'asr'])
    e.vad.mode = 'local'
    e.kws.mode = valid('kws').length ? 'local' : 'api'
    e.asr.mode = 'local'

    if (scope === 'recognition') {
      notify.ok('已切换为本地识别（保存中）')
      void s.saveModule('recognition')
      return
    }

    const ttsReady = (models.value.tts || []).some(
      (m) => m.valid && m.path === e.tts.local_model,
    )
    e.tts.mode = ttsReady ? 'local' : 'api'
    ttsSettings.value.engine = ttsReady ? 'local' : 'api'
    saveTts()
    if (!ttsReady) notify.warn('Kokoro 本地 TTS 未就位，TTS 暂用 API；下载后再次一键本地即可')
    notify.ok('已切换为本地语音（保存中）')
    void s.saveModule('models')
  }

  /** 扫描模型 / 硬件 / 能力并拉各能力 schema。Scan models, hardware, capabilities and schemas. */
  async function refresh() {
    loading.value = true
    try {
      const [m, h, c] = await Promise.all([
        api.getModels(), api.getHardware(), api.getCapabilities(),
      ])
      if (m.ok) models.value = m.models
      if (h.ok) hw.value = h.hardware
      if (c.ok) caps.value = c
      ensureSelection()
      // 按当前选中的模型拉 schema（字段/默认值随家族变化）。
      // Fetch schema per the currently selected model (fields/defaults vary by family).
      const modelOf = (k: ModelKind): string => {
        const e = s.ed()
        return MODEL_KEYS[k] ? String(e?.[k]?.[MODEL_KEYS[k]] || '') : ''
      }
      const schemaResults = await Promise.all(
        (['vad', 'kws', 'asr', 'tts'] as const).map(k =>
          api.getSchema(k, modelOf(k)).catch(() => null)),
      )
      schemaResults.forEach((r, i) => {
        if (r?.ok) schemas.value[['vad', 'kws', 'asr', 'tts'][i]] = r.params
      })
      await refreshDevices(false)
    } catch (e: any) {
      notify.err('模型扫描失败：' + (e?.message || e))
    } finally {
      loading.value = false
    }
  }

  /** 枚举浏览器音频设备。Enumerate browser audio devices. */
  async function refreshDevices(askPermission = false) {
    try {
      if (askPermission) {
        // 只有用户点「刷新设备列表」才请求权限；打开设置页不弹权限框。
        // Ask for permission only on the explicit refresh click; opening settings must not prompt.
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        stream.getTracks().forEach((t) => t.stop())
      }
      devices.value = await navigator.mediaDevices.enumerateDevices()
    } catch (e: any) {
      notify.warn('无法读取音频设备：' + (e?.message || e))
    }
  }

  const inputOptions = computed(() => [
    { value: '', label: '系统默认' },
    ...devices.value.filter((d) => d.kind === 'audioinput')
      .map((d, i) => ({ value: d.deviceId, label: d.label || `麦克风 ${i + 1}` })),
  ])
  const outputOptions = computed(() => [
    { value: '', label: '系统默认' },
    ...devices.value.filter((d) => d.kind === 'audiooutput')
      .map((d, i) => ({ value: d.deviceId, label: d.label || `扬声器 ${i + 1}` })),
  ])

  return {
    models, schemas, engineTests, testing, hw, caps, devices, loading,
    providers, currentWakeWords, inputOptions, outputOptions,
    testKindsFor, statusRowsFor, schemaFor, modelOptions, missingHint,
    switchModel, testEngine, refresh, refreshDevices, oneClickLocal,
  }
}
