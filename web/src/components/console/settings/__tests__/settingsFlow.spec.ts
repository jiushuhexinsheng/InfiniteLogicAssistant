import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../../api', () => ({
  api: {
    getConfigFull: vi.fn(),
    patchConfig: vi.fn(),
    getDetection: vi.fn(),
  },
}))
vi.mock('../../../../composables/useApi', () => {
  const refreshConfig = vi.fn()
  return { useConfig: () => ({ refreshConfig, config: {} }) }
})
vi.mock('../../../../composables/useToast', () => ({
  notify: { ok: vi.fn(), err: vi.fn(), warn: vi.fn(), info: vi.fn(), dismiss: vi.fn(), clear: vi.fn() },
}))

import { api } from '../../../../api'
import { notify } from '../../../../composables/useToast'
import { editable, load, moduleBody, saveModule, saving } from '../state'

/**
 * 设置读写真通（2026-10-11 验收）：load 回填快照、active 兜底、各模块 PATCH body
 * 形状正确、保存成功/失败反馈与 saving 复位 —— 这些是「各种设置是否真的正常」的
 * 前端半程（后端 PATCH 持久化由 tests/server/test_server_settings.py 覆盖）。
 *
 * Settings read/write actually works (2026-10-11 acceptance): load backfills the
 * snapshot, active falls back, per-module PATCH bodies are well-formed, save
 * success/failure feedback fires and saving resets — the frontend half of "do the
 * settings actually work" (the backend PATCH persistence half is covered by
 * tests/server/test_server_settings.py).
 */

function fullSnapshot(llmActive = 'ds') {
  const prof = { provider: 'openai', endpoint: 'https://x', model: 'm', chat_path: '/v1/chat/completions', models: [] }
  return {
    llm: { active: llmActive, profiles: { ds: { ...prof }, other: { ...prof } }, api_key_set: { ds: false, other: false } },
    asr: { active: 'a', profiles: { a: { ...prof } }, api_key_set: { a: false } },
    tts: { enabled: false, active: 't', profiles: { t: { ...prof } }, api_key_set: { t: false } },
    wake_word: { enabled: true, keywords: ['衍衡'], sensitivity: 0.5, model_path: '' },
    vad: { silence_threshold: 0.02, listen_idle_s: 180 },
    permissions: { default_action: 'allow', tiers: { read: 'allow', write: 'allow', exec: 'allow' }, rules: [] },
    agent: { recursion_limit: 12 }, llm_client: {}, tools: {}, rag: {}, memory: {},
    server: { host: '127.0.0.1', port: 8520, open_browser: true, cors_origins: [] },
    mcp: { servers: [] },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  editable.value = null
})

describe('load 加载', () => {
  it('回填 editable 且坏 active 回退到第一个 profile', async () => {
    vi.mocked(api.getConfigFull).mockResolvedValue({ ok: true, editable: fullSnapshot('gone') } as any)
    await load()
    expect(editable.value).not.toBeNull()
    expect((editable.value as any).llm.active).toBe('ds')   // 'gone' → 第一个
    expect((editable.value as any).vad.listen_idle_s).toBe(180)
  })

  it('后端失败 → notify.err 且 editable 不动', async () => {
    editable.value = null
    vi.mocked(api.getConfigFull).mockResolvedValue({ ok: false, error: 'boom' } as any)
    await load()
    expect(notify.err).toHaveBeenCalled()
    expect(editable.value).toBeNull()
  })
})

describe('moduleBody 各模块 PATCH 形状', () => {
  beforeEach(() => {
    editable.value = fullSnapshot() as any
  })

  it('llm → {active, profiles}；voice → {wake_word, vad}；permissions 原样', () => {
    expect(Object.keys(moduleBody('llm'))).toEqual(['llm'])
    expect((moduleBody('llm') as any).llm.active).toBe('ds')
    expect(Object.keys(moduleBody('voice')).sort()).toEqual(['vad', 'wake_word'])
    expect(moduleBody('permissions')).toHaveProperty('permissions')
  })

  it('advanced → 各高级段 + server 子集（只带 host/port/open_browser/cors）', () => {
    const b = moduleBody('advanced') as any
    expect(Object.keys(b).sort()).toEqual(['agent', 'llm_client', 'mcp', 'memory', 'rag', 'server', 'tools'])
    expect(Object.keys(b.server).sort()).toEqual(['cors_origins', 'host', 'open_browser', 'port'])
  })

  it('tts → {tts:{enabled, active, profiles}}', () => {
    const b = moduleBody('tts') as any
    expect(Object.keys(b.tts).sort()).toEqual(['active', 'enabled', 'profiles'])
  })
})

describe('saveModule 保存', () => {
  beforeEach(() => {
    editable.value = fullSnapshot() as any
    vi.mocked(api.patchConfig).mockResolvedValue({ ok: true } as any)
  })

  it('成功 → patchConfig 收到 body、notify.ok、saving 复位', async () => {
    await saveModule('llm')
    expect(api.patchConfig).toHaveBeenCalledWith(expect.objectContaining({
      llm: expect.objectContaining({ active: 'ds' }),
    }))
    expect(notify.ok).toHaveBeenCalled()
    expect(saving.value).toBe(false)
  })

  it('restart_required → 追加重启提示', async () => {
    vi.mocked(api.patchConfig).mockResolvedValue({ ok: true, restart_required: true } as any)
    await saveModule('advanced')
    expect(notify.warn).toHaveBeenCalled()
    expect(saving.value).toBe(false)
  })

  it('失败 → notify.err 且 saving 复位', async () => {
    vi.mocked(api.patchConfig).mockResolvedValue({ ok: false, error: '无效配置' } as any)
    await saveModule('llm')
    expect(notify.err).toHaveBeenCalled()
    expect(saving.value).toBe(false)
  })

  it('未加载快照时直接返回（不发请求）', async () => {
    editable.value = null
    await saveModule('llm')
    expect(api.patchConfig).not.toHaveBeenCalled()
  })
})
