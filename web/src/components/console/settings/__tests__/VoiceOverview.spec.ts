// @vitest-environment jsdom
/** 语音概览仪表盘：7 卡分组、就绪计数、模式徽章、测试全部、点击跳转。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  status: {
    value: {
      vad: { mode: 'local', present: true, ready: true, reason: '' },
      kws: { mode: 'local', present: true, ready: true, reason: '' },
      asr: { mode: 'cloud', present: true, ready: true, reason: '' },
      tts: { mode: 'local', present: true, ready: true, reason: '' },
    } as any,
  },
  refresh: vi.fn(),
  config: {
    value: {
      llm_available: true,
      llm_profile: 'xiaomi-mimo-llm',
      tts_mode: 'local',
      wake_word: { keywords: ['衍衡', '洛吉斯'] },
      asr_mode: 'cloud',
    },
  },
  engine: { value: 'local' },
  getHardware: vi.fn().mockResolvedValue({
    ok: true,
    hardware: { providers: ['cpu'], cpu_count: 8, sherpa_version: '1.13.8' },
  }),
  testEngine: vi.fn().mockResolvedValue({ ok: true, ready: true, latency_ms: 12, detail: 'OK' }),
}))

vi.mock('../../../../composables/useApi', () => ({
  useConfig: () => ({ config: mocks.config }),
}))
vi.mock('../../../../composables/useVoiceModuleStatus', () => ({
  useVoiceModuleStatus: () => ({ status: mocks.status, refreshVoiceStatus: mocks.refresh }),
}))
vi.mock('../../../../composables/assistant/useTts', () => ({
  ttsSettings: mocks.engine,
}))
vi.mock('../../../../api', () => ({
  api: { getHardware: mocks.getHardware, testEngine: mocks.testEngine },
}))

import VoiceOverview from '../VoiceOverview.vue'

describe('VoiceOverview', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {} })
    mocks.getHardware.mockClear()
    mocks.testEngine.mockClear()
    mocks.refresh.mockClear()
  })

  it('渲染 7 张分组能力卡与就绪计数', async () => {
    const w = mount(VoiceOverview)
    await flushPromises()

    expect(w.findAll('.voice-tile')).toHaveLength(7)
    expect(w.findAll('.vt-arrow')).toHaveLength(6)
    expect(w.text()).toContain('输入')
    expect(w.text()).toContain('理解')
    expect(w.text()).toContain('输出')
    expect(w.find('.vo-score').text()).toContain('7/7')
    expect(w.find('.vo-chips').text()).toContain('云端')
    expect(w.text()).toContain('衍衡')
    expect(w.text()).toContain('sherpa-onnx 1.13.8')
  })

  it('能力卡按目标发出 select', async () => {
    const w = mount(VoiceOverview)
    await flushPromises()
    const tiles = w.findAll('.voice-tile')
    await tiles[3].trigger('click')    // ASR → 识别
    await tiles[4].trigger('click')    // LLM → 大模型
    await tiles[5].trigger('click')    // TTS → 合成

    expect(w.emitted('select')?.[0]).toEqual(['recognition'])
    expect(w.emitted('select')?.[1]).toEqual(['llm'])
    expect(w.emitted('select')?.[2]).toEqual(['synthesis'])
  })

  it('测试全部引擎并显示自检结果', async () => {
    const w = mount(VoiceOverview)
    await flushPromises()

    await w.find('.vo-test-all').trigger('click')
    await flushPromises()

    expect(mocks.testEngine).toHaveBeenCalledTimes(4)
    expect(w.text()).toContain('自检')
    expect(w.text()).toContain('12ms')
  })
})
