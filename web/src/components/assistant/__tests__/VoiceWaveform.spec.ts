// @vitest-environment jsdom
/** 单块滚动波形：条数与活跃态。Single waveform: bar count and active state. */
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { resetMicLevel, reportMicLevel } from '../../../composables/assistant/micLevel'
import VoiceWaveform from '../VoiceWaveform.vue'

describe('VoiceWaveform', () => {
  beforeEach(() => resetMicLevel())

  it('渲染连续波形路径（不再分割成柱）并带活跃态', () => {
    reportMicLevel(0.2)
    const w = mount(VoiceWaveform, { props: { active: true } })
    expect(w.findAll('.vw-bar')).toHaveLength(0)
    expect(w.findAll('path').length).toBeGreaterThan(0)
    expect(w.find('.voice-waveform').classes()).toContain('active')
  })

  it('非活跃态变暗', () => {
    const w = mount(VoiceWaveform, { props: { active: false } })
    expect(w.find('.voice-waveform').classes()).toContain('dim')
  })
})
