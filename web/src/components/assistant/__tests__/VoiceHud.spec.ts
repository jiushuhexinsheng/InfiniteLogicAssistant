// @vitest-environment jsdom
/** 语音条 v3：空闲只留胶囊，有识别文本才向右伸出文本段；状态图标化/缩小。 */
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import { callActive, state, statusLine } from '../../../composables/assistant/store'
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
    state.value = 'idle'
    statusLine.value = ''
    callActive.value = false
    setStreamPhase('ready')
  })

  it('空闲只显示原胶囊，不伸出文本段', () => {
    const w = mountHud()
    expect(w.find('.vh-pill').text()).toContain('双击开启语音')
    expect(w.find('.vh-box').exists()).toBe(false)
  })

  it('聆听态状态压成小字，无文本时不伸段', () => {
    state.value = 'listening'
    const w = mountHud()
    expect(w.find('.vh-pill').text()).toContain('聆听')
    expect(w.find('.vh-box').exists()).toBe(false)
  })

  it('识别中向右伸出文本段：角色行只有「衍衡」，不显示引擎走向', () => {
    state.value = 'transcribing'
    setInterim('帮我查一下天气', 1)
    const w = mountHud()
    const box = w.find('.vh-box')
    expect(box.exists()).toBe(true)
    expect(box.find('.vh-role').text()).toBe('衍衡')
    expect(box.text()).not.toContain('KWS')
    expect(box.find('.vh-text').text()).toContain('帮我查一下天气')
    expect(box.find('.vh-caret').exists()).toBe(true)
  })

  it('可提交时转绿并显示勾', () => {
    liveTranscript.value = {
      ...liveTranscript.value, status: 'finalized', finalText: '查天气', interim: '',
    }
    markHudAccepted()
    const w = mountHud()
    expect(w.find('.voice-hud').classes()).toContain('ready')
    expect(w.find('.vh-check').exists()).toBe(true)
    expect(w.text()).not.toContain('已提交')
  })

  it('旁白用虚线框，且不显示「未进入对话」说明', () => {
    liveTranscript.value = {
      ...liveTranscript.value, status: 'finalized', finalText: '', ghostText: '电视声',
    }
    hudOutcome.value = 'ghost'
    const w = mountHud()
    expect(w.find('.voice-hud').classes()).toContain('ghost')
    expect(w.find('.vh-pill').text()).toContain('旁白')
    expect(w.text()).toContain('电视声')
    expect(w.text()).not.toContain('未进入对话')
    expect(w.text()).not.toContain('未上传')
  })

  it('回复阶段只保留胶囊状态，不展开文本段', () => {
    const w = mountHud({ state: 'responding' })
    expect(w.find('.vh-pill').text()).toContain('回复')
    expect(w.find('.vh-box').exists()).toBe(false)
  })

  it('通话模式显示独立「通话中」徽章', () => {
    state.value = 'listening'
    callActive.value = true
    const w = mountHud()
    expect(w.find('.vsb').classes()).toContain('k-call')
    expect(w.find('.vsb-label').text()).toBe('通话中')
  })

  it('点击发出 open', async () => {
    const w = mountHud()
    await w.find('.voice-hud').trigger('click')
    expect(w.emitted('open')).toHaveLength(1)
  })
})
