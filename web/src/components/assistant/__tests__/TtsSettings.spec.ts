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
 * 卡2 只含播放偏好（只读 Profile/模型徽章 + 音色覆盖 + 音量）。语速/音调不在
 * 播放偏好：后端 /api/tts 只接受 text + voice；语速走合成卡本地 Kokoro 的 speed。
 *
 * Card 2 holds only playback prefs (read-only profile/model badges + voice override +
 * volume). No rate/pitch: the backend /api/tts accepts only text + voice; speed lives
 * in the local Kokoro card.
 */
describe('TtsSettings 播放偏好', () => {
  beforeEach(() => {
    ttsSettings.value.engine = 'local'
    saveTts()
    configRef.value = { tts_profile: 'mimo', tts_model: 'mimo-v2.5-tts' }
  })

  it('渲染只读徽章 + 音色 + 音量，无语速/音调', () => {
    const w = mount(TtsSettings)
    const text = w.text()
    expect(text).toContain('Profile')
    expect(text).toContain('mimo')
    expect(text).toContain('mimo-v2.5-tts')
    expect(text).toContain('音量')
    expect(text).toContain('音色')
    expect(text).not.toContain('语速')
    expect(text).not.toContain('音调')
    // 音色为下拉（VoiceSelect → UiSelect，点开即选）。Voice is a dropdown (VoiceSelect → UiSelect).
    expect(w.find('.voice-select .ui-select').exists()).toBe(true)
  })

  it('voiceclone 模型：音色由后端决定，显示克隆说明而非下拉', () => {
    configRef.value = { tts_profile: 'mimo', tts_model: 'mimo-v2.5-tts-voiceclone' }
    const w = mount(TtsSettings)
    expect(w.find('.voice-select .ui-select').exists()).toBe(false)
    expect(w.text()).toContain('voice_ref')
  })

  it('不再包含引擎切换与播报开关（属卡1）', () => {
    const w = mount(TtsSettings)
    expect(w.find('.tts-engine').exists()).toBe(false)
    expect(w.find('.eng-btn').exists()).toBe(false)
    expect(w.text()).not.toContain('试听')
  })
})
