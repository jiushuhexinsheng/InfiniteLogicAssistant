// @vitest-environment jsdom
/**
 * TTS 引擎切换：只有真的变化（或后端模式不一致）才写配置 —— 避免无谓的
 * PATCH /api/config 触发整段热重载、把本地引擎和子进程池全部重建。
 *
 * TTS engine switching: only a real change (or a backend mismatch) writes config,
 * so a no-op click cannot trigger a full reload that rebuilds local engines/pools.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  patchConfig: vi.fn().mockResolvedValue({ ok: true, restart_required: false }),
  refreshConfig: vi.fn().mockResolvedValue(undefined),
  config: { value: null as null | { tts_mode?: string } },
}))

vi.mock('../../../api', () => ({ api: { patchConfig: mocks.patchConfig } }))
vi.mock('../../useApi', () => ({
  useConfig: () => ({ config: mocks.config, refreshConfig: mocks.refreshConfig }),
}))

import { useTtsEngine } from '../useTtsEngine'
import { ttsSettings } from '../useTts'

describe('useTtsEngine.setEngine', () => {
  beforeEach(() => {
    mocks.patchConfig.mockClear()
    mocks.refreshConfig.mockClear()
    localStorage.clear()
  })

  it('点当前引擎且后端已是该模式 → 不发 PATCH', () => {
    ttsSettings.value.engine = 'api'
    mocks.config.value = { tts_mode: 'api' }

    useTtsEngine().setEngine('api')

    expect(mocks.patchConfig).not.toHaveBeenCalled()
  })

  it('本地意图未变但后端模式不一致 → 仍要 PATCH 纠正', () => {
    ttsSettings.value.engine = 'api'
    mocks.config.value = { tts_mode: 'local' }

    useTtsEngine().setEngine('api')

    expect(mocks.patchConfig).toHaveBeenCalledWith({ tts: { mode: 'api' } })
  })

  it('真正切换引擎 → PATCH 并刷新配置', async () => {
    ttsSettings.value.engine = 'api'
    mocks.config.value = { tts_mode: 'api' }

    useTtsEngine().setEngine('local')
    await Promise.resolve()

    expect(ttsSettings.value.engine).toBe('local')
    expect(mocks.patchConfig).toHaveBeenCalledWith({ tts: { mode: 'local' } })
    expect(mocks.refreshConfig).toHaveBeenCalled()
  })
})
