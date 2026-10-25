// @vitest-environment jsdom
/** 语音 HUD：聆听/识别/可提交/旁白/回复状态与点击打开。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../../../composables/useApi', () => ({
  useConfig: () => ({
    config: { value: { kws_mode: 'local', asr_mode: 'cloud' } },
  }),
}))

import { state, statusLine } from '../../../composables/assistant/store'
import {
  clearTranscript, hudOutcome, liveTranscript, markHudAccepted,
  setInterim, setStreamPhase,
} from '../../../composables/assistant/storeTranscript'
import VoiceHud from '../VoiceHud.vue'

const VISUAL = { icon: 'wave', color: '#67e8f9', label: '', grad: '' } as any

function mountHud(over: Record<string, unknown> = {}) {
  return mount(VoiceHud, {
    props: { state: state.value, visual: VISUAL, wakeHint: '衍衡', visible: true, side: 'right', ...over },
  })
}

describe('VoiceHud', () => {
  beforeEach(() => {
    clearTranscript()
    state.value = 'listening'
    statusLine.value = ''
    setStreamPhase('ready')
  })

  it('聆听态显示唤醒提示与实时波形', () => {
    const w = mountHud()
    expect(w.text()).toContain('聆听中')
    expect(w.text()).toContain('衍衡')
    expect(w.find('.voice-waveform').classes()).toContain('active')
    expect(w.text()).toContain('本地 KWS')
  })

  it('识别中显示中间稿与光标', () => {
    setInterim('帮我查一下天气', 1)
    const w = mountHud({ state: 'transcribing' })
    expect(w.text()).toContain('正在识别')
    expect(w.text()).toContain('帮我查一下天气')
    expect(w.find('.vh-caret').exists()).toBe(true)
  })

  it('可提交时转绿并出现 → LLM 芯片', () => {
    liveTranscript.value = {
      ...liveTranscript.value, status: 'finalized', finalText: '查天气', interim: '',
    }
    markHudAccepted()
    const w = mountHud()
    expect(w.find('.voice-hud').classes()).toContain('ready')
    expect(w.text()).toContain('已提交')
    expect(w.find('.vh-chip.green').exists()).toBe(true)
  })

  it('旁白显示未进入对话且不显示回复文本', () => {
    liveTranscript.value = {
      ...liveTranscript.value, status: 'finalized', finalText: '', ghostText: '电视声',
    }
    hudOutcome.value = 'ghost'
    const w = mountHud()
    expect(w.find('.voice-hud').classes()).toContain('ghost')
    expect(w.text()).toContain('未进入对话')
    expect(w.text()).toContain('电视声')
  })

  it('回复阶段只显示状态，不显示回复内容', () => {
    const w = mountHud({ state: 'responding' })
    expect(w.text()).toContain('正在回复')
    expect(w.find('.vh-text').text()).toBe('')
  })

  it('点击发出 open', async () => {
    const w = mountHud()
    await w.find('.voice-hud').trigger('click')
    expect(w.emitted('open')).toHaveLength(1)
  })
})
