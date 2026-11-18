// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

vi.mock('../../../../api', () => ({
  api: {
    getConfigFull: vi.fn(),
    patchConfig: vi.fn(),
    getDetection: vi.fn(),
    getModels: vi.fn(),
    getHardware: vi.fn(),
    getCapabilities: vi.fn(),
    getSchema: vi.fn(),
    testEngine: vi.fn(),
  },
}))
vi.mock('../../../../composables/useToast', () => ({
  notify: { ok: vi.fn(), err: vi.fn(), warn: vi.fn(), info: vi.fn() },
}))
vi.mock('../../../../composables/useApi', () => ({
  useConfig: () => ({ refreshConfig: vi.fn(), config: {} }),
}))
vi.mock('../../../../composables/useVoiceModuleStatus', async () => {
  const { ref, computed } = await import('vue')
  return {
    status: ref(null),
    voiceAllReady: computed(() => false),
    refreshVoiceStatus: vi.fn(async () => {}),
    useVoiceModuleStatus: () => ({ status: ref(null), refreshVoiceStatus: vi.fn() }),
  }
})

import { api } from '../../../../api'
import { editable } from '../state'
import { useLocalModels } from '../useLocalModels'

/**
 * useLocalModels（从 LocalModelsCard 抽出的共享状态）单测：
 * 状态行按段落裁剪、自检能力按模式筛选、一键本地不越界改 TTS。
 *
 * Unit tests for useLocalModels (state extracted from LocalModelsCard): per-scope status
 * rows, self-test kinds by mode, and one-click-local never crossing into TTS.
 */

/** 最小可编辑快照：四能力字段齐全且与模型清单路径一致。Minimal editable snapshot. */
function snapshot() {
  const svc = { active: 'p', profiles: { p: { provider: 'openai', endpoint: '', model: '' } }, api_key_set: { p: false } }
  return {
    llm: structuredClone(svc),
    asr: { ...structuredClone(svc), mode: 'local', local_model: 'models/asr/a', streaming: true,
           provider: 'cpu', device: 0, num_threads: 0 },
    tts: { enabled: true, active: 'p', profiles: { p: { provider: 'openai', voices: [], format: 'wav' } },
           api_key_set: { p: false }, mode: 'local', local_model: 'models/tts/t', provider: 'cpu',
           device: 0, num_threads: 0, speaker: 0, speed: 1, lang: '' },
    wake_word: { enabled: true, keywords: ['衍衡'], sensitivity: 0.5, model_path: '' },
    vad: { mode: 'local', engine: 'ten-vad', model: 'models/vad/v', provider: 'cpu',
           device: 0, num_threads: 0, silence_threshold: 0.02, followup_window_ms: 6000 },
    kws: { enabled: true, mode: 'local', model_dir: 'models/kws/k', provider: 'cpu', device: 0,
           num_threads: 2, keywords_threshold: 0.25, keywords_score: 1 },
    streaming: { enabled: true, partial_interval_ms: 120, endpoint_silence_ms: 700, max_utterance_ms: 15000 },
    hardware: { input_device: '', output_device: '', echo_cancellation: true,
                noise_suppression: true, auto_gain: true },
    permissions: { default_action: 'allow', tiers: { read: 'allow', write: 'allow', exec: 'allow' }, rules: [] },
    agent: {}, llm_client: {}, tools: {}, mcp: { servers: [] }, rag: {}, memory: {},
    server: { host: '127.0.0.1', port: 8520, open_browser: false, cors_origins: [], api_token_set: false },
  } as any
}

const MODELS = {
  vad: [{ path: 'models/vad/v', name: 'v', valid: true }],
  kws: [{ path: 'models/kws/k', name: 'k', valid: true }],
  asr: [{ path: 'models/asr/a', name: 'a', valid: true }],
  tts: [{ path: 'models/tts/t', name: 't', valid: true }],
}

beforeEach(() => {
  vi.clearAllMocks()
  editable.value = snapshot()
  vi.mocked(api.getModels).mockResolvedValue({ ok: true, models: MODELS } as any)
  vi.mocked(api.getHardware).mockResolvedValue({
    ok: true, hardware: { providers: ['cpu'], cpu_count: 8, sherpa_version: '1.13.8' },
  } as any)
  vi.mocked(api.getCapabilities).mockResolvedValue({
    ok: true,
    vad: { mode: 'local', present: true },
    kws: { mode: 'local', present: true },
    asr: { mode: 'local', present: true },
    tts: { mode: 'local', present: true },
  } as any)
  vi.mocked(api.getSchema).mockResolvedValue({ ok: true, params: [] } as any)
  vi.mocked(api.patchConfig).mockResolvedValue({ ok: true, restart_required: false } as any)
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { enumerateDevices: vi.fn(async () => []) },
  })
})

describe('useLocalModels 状态与自检', () => {
  it('状态行按段落裁剪：识别页只有 VAD/KWS/ASR，合成页只有 TTS', async () => {
    const m = useLocalModels()
    await m.refresh()

    const rec = m.statusRowsFor('recognition')
    expect(rec.map(r => r.kind)).toEqual(['VAD', 'KWS', 'ASR'])
    expect(rec.some(r => r.kind === 'TTS')).toBe(false)
    expect(m.statusRowsFor('tts').map(r => r.kind)).toEqual(['TTS'])
  })

  it('自检能力随模式收敛：TTS 本地才有、ASR 云端不出现', async () => {
    const m = useLocalModels()
    await m.refresh()

    expect(m.testKindsFor('tts')).toEqual(['tts'])
    expect(m.testKindsFor('recognition')).toEqual(['vad', 'kws', 'asr'])

    editable.value.asr.mode = 'cloud'
    expect(m.testKindsFor('recognition')).toEqual(['vad', 'kws'])

    editable.value.tts.mode = 'cloud'
    expect(m.testKindsFor('tts')).toEqual([])
  })

  it('模型缺失 → err 色调与「模型缺失」文案', async () => {
    vi.mocked(api.getCapabilities).mockResolvedValue({
      ok: true,
      vad: { mode: 'local', present: false },
      kws: { mode: 'local', present: true },
      asr: { mode: 'local', present: true },
      tts: { mode: 'local', present: true },
    } as any)
    const m = useLocalModels()
    await m.refresh()

    const rows = m.statusRowsFor('recognition')
    expect(rows[0]).toMatchObject({ kind: 'VAD', tone: 'err' })
    expect(rows[0].text).toContain('模型缺失')
  })

  it('一键本地（识别）只改三能力并保存识别模块，不碰 TTS', async () => {
    const m = useLocalModels()
    await m.refresh()
    editable.value.tts.mode = 'api'

    m.oneClickLocal('recognition')
    await flushPromises()

    expect(editable.value.vad.mode).toBe('local')
    expect(editable.value.kws.mode).toBe('local')
    expect(editable.value.asr.mode).toBe('local')
    expect(editable.value.tts.mode).toBe('api')
    const body = vi.mocked(api.patchConfig).mock.calls.at(-1)?.[0] as Record<string, any>
    expect(body).toHaveProperty('asr')
    expect(body).toHaveProperty('vad')
    expect(body).toHaveProperty('kws')
  })
})
