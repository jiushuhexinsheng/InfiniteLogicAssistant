// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

/** 可控的 /api/config 桩：tts_profile / tts_model 由各测试设定。
 *  Controllable /api/config stub: tests set tts_profile / tts_model. */
const configRef = { value: null as any }
vi.mock('../../../composables/useApi', () => ({
  useConfig: () => ({ config: configRef, initConfig: vi.fn(), refreshConfig: vi.fn() }),
}))

import TtsSettings from '../TtsSettings.vue'
import { ttsSettings, saveTts } from '../../../composables/assistant/useTts'

/**
 * 卡2 按引擎渲染设置组（引擎选择已上移到卡1 TtsEngineCard）。
 *
 * 回归靶子：本地组（声音/音量/语速/音调）只在 browser 引擎出现；API 组
 * （只读 Profile/模型徽章 + 音色覆盖 + 音量）只在 api 引擎出现，且不得出现
 * 语速/音调（后端 /api/tts 无 rate/pitch 参数）。
 *
 * Card 2 renders the settings group per engine (the engine picker moved up to
 * card 1 / TtsEngineCard).
 */
describe('TtsSettings 引擎分组', () => {
  beforeEach(() => {
    ttsSettings.value.engine = 'browser'
    saveTts()
    configRef.value = { tts_profile: 'mimo', tts_model: 'mimo-v2.5-tts' }
  })

  /** 本地引擎：声音/语速/音调可见，无徽章。Local engine: voice/rate/pitch visible, no badges. */
  it('browser 引擎：渲染本地设置组，隐藏 API 组', () => {
    const w = mount(TtsSettings)
    const text = w.text()
    expect(text).toContain('声音')
    expect(text).toContain('语速')
    expect(text).toContain('音调')
    expect(text).not.toContain('Profile')
    expect(w.find('.ui-select').exists()).toBe(true)
    // 滑块已迁移至 UiRange（.ui-range）。Sliders migrated to UiRange.
    expect(w.findAll('.ui-range').length).toBe(3)
  })

  /** API 引擎：徽章 + 音色 + 音量，无语速/音调。API engine: badges + voice + volume, no rate/pitch. */
  it('api 引擎：渲染 API 设置组与只读徽章，隐藏语速/音调', () => {
    ttsSettings.value.engine = 'api'
    saveTts()
    const w = mount(TtsSettings)
    const text = w.text()
    expect(text).toContain('Profile')
    expect(text).toContain('mimo')
    expect(text).toContain('mimo-v2.5-tts')
    expect(text).toContain('音量')
    expect(text).toContain('音色')
    expect(text).not.toContain('语速')
    expect(text).not.toContain('音调')
    // 音色为下拉（VoiceSelect → UiSelect，点开即选）。Voice is a dropdown (VoiceSelect → UiSelect, open-to-pick).
    expect(w.find('.voice-select .ui-select').exists()).toBe(true)
    expect(w.find('.vs-label em').exists()).toBe(true)
  })

  /** 引擎选择本身不在本组件（已上移卡1）。The engine picker is not in this component (moved to card 1). */
  it('不再包含引擎切换与播报开关（属卡1）', () => {
    const w = mount(TtsSettings)
    expect(w.find('.tts-engine').exists()).toBe(false)
    expect(w.find('.eng-btn').exists()).toBe(false)
    expect(w.find('.tts-row').exists()).toBe(false)
    expect(w.text()).not.toContain('试听')
  })
})
