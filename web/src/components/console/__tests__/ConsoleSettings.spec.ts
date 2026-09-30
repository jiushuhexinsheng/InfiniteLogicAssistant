// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: {
    getConfigFull: vi.fn(),
    getProviders: vi.fn(),
    patchConfig: vi.fn(),
    getDetection: vi.fn(),
    putSecret: vi.fn(),
    fetchModels: vi.fn(),
  },
}))
// 播报面板自带 SpeechSynthesis 接线，与「区块落位」断言无关，替换成可识别的桩。
// The playback panel carries its own speech-synthesis wiring, irrelevant to placement assertions; stub it.
vi.mock('../../assistant/TtsSettings.vue', () => ({
  default: { template: '<div class="tts-settings-stub" />' },
}))

import { api } from '../../../api'
import { activeMenu, editable } from '../settings/state'
import { ttsSettings, saveTts } from '../../../composables/assistant/useTts'
import ConsoleSettings from '../ConsoleSettings.vue'

/** 最小可编辑快照：llm/asr/tts 三段都要在（菜单绿点与 ServiceCard 都会读）。
 *  Minimal editable snapshot: all three service sections (menu dots and ServiceCard read them). */
function snapshot() {
  const svc = { active: 'p', profiles: { p: {} }, api_key_set: { p: false } }
  return {
    llm: structuredClone(svc),
    asr: structuredClone(svc),
    tts: { enabled: true, active: 'p', profiles: { p: { provider: 'openai', voices: [], format: 'wav' } }, api_key_set: { p: false } },
    wake_word: { enabled: true, keywords: ['衍衡'], sensitivity: 0.5, model_path: '' },
    vad: {
      silence_threshold: 0.02, silence_duration_ms: 1500, max_duration_ms: 10000,
      answer_timeout_ms: 8000, min_speech_ms: 300, upload_throttle_ms: 500, followup_window_ms: 6000,
      barge_in: false,
    },
  }
}

/**
 * 语音合成的两卡堆叠结构。
 *
 * 回归靶子：卡1（引擎大选择 + 播报开关 + 试听）常驻；卡2 按引擎分支 ——
 * 本地渲染浏览器语音卡，API 渲染 ServiceCard（含 voice_ref / voices 字段）。
 * 任何把结构拍回单卡、或丢掉某一分支的改动都应被此处拦下。
 *
 * Two-card stacked structure for the TTS section.
 */
describe('ConsoleSettings 语音合成两卡结构', () => {
  beforeEach(async () => {
    vi.mocked(api.getConfigFull).mockResolvedValue({ ok: true, editable: snapshot() } as any)
    vi.mocked(api.getProviders).mockResolvedValue({ ok: true, catalog: {} } as any)
    editable.value = null
    activeMenu.value = 'tts'
    ttsSettings.value.engine = 'browser'
    saveTts()
  })

  /** 本地分支：卡1 引擎选择 + 卡2 本地语音卡，无后端 ServiceCard。
   *  Local branch: card 1 engine picker + card 2 local card, no backend ServiceCard. */
  it('本地引擎：渲染引擎选择卡与本地语音卡', async () => {
    const w = mount(ConsoleSettings)
    await flushPromises()
    expect(w.text()).toContain('语音引擎')
    // 引擎大选择已迁移至 UiRadioCard（.ui-radio-cards）。Engine picker migrated to UiRadioCard.
    expect(w.find('.ui-radio-cards').exists()).toBe(true)
    expect(w.text()).toContain('本地语音 · 浏览器合成')
    expect(w.text()).not.toContain('TTS 语音合成')
    expect(w.find('.tts-settings-stub').exists()).toBe(true)
  })

  /** 两卡顺序：引擎选择卡在前，配置卡在后。Order: engine card first, config card second. */
  it('引擎选择卡位于配置卡之前', async () => {
    const w = mount(ConsoleSettings)
    await flushPromises()
    const cards = w.findAll('.ui-card')
    expect(cards.length).toBeGreaterThanOrEqual(2)
    expect(cards[0].text()).toContain('语音引擎')
    expect(cards[1].text()).toContain('本地语音 · 浏览器合成')
  })

  /** API 分支：ServiceCard（含 voice_ref / voices 字段）+ 播报面板挂 slot。
   *  API branch: ServiceCard (with voice_ref / voices fields) + playback panel in slot. */
  it('API 引擎：渲染后端配置卡与新增字段', async () => {
    ttsSettings.value.engine = 'api'
    saveTts()
    const w = mount(ConsoleSettings)
    await flushPromises()
    expect(w.text()).toContain('语音引擎')
    expect(w.text()).toContain('TTS 语音合成')
    expect(w.text()).toContain('参考音频（voiceclone）')
    expect(w.text()).toContain('音色列表（下拉候选）')
    expect(w.find('.tts-settings-stub').exists()).toBe(true)
  })

  /** 语音唤醒：两卡与播报面板都不得出现。Voice section: neither card nor panel appears. */
  it('语音唤醒菜单不渲染语音合成的卡', async () => {
    activeMenu.value = 'voice'
    const w = mount(ConsoleSettings)
    await flushPromises()
    expect(w.find('.tts-settings-stub').exists()).toBe(false)
    expect(w.find('.ui-radio-cards').exists()).toBe(false)
    expect(w.text()).toContain('唤醒词')
  })
})
