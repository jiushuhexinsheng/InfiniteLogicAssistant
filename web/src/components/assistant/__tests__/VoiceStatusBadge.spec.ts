// @vitest-environment jsdom
/** 语音状态徽章：每种状态独立颜色/动效与文案。 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import VoiceStatusBadge from '../VoiceStatusBadge.vue'

describe('VoiceStatusBadge', () => {
  it.each([
    ['idle', '双击开启语音'],
    ['listening', '聆听'],
    ['call', '通话中'],
    ['command', '请说'],
    ['recognizing', '识别'],
    ['ready', '就绪'],
    ['ghost', '旁白'],
    ['thinking', '思考'],
    ['tool', '工具'],
    ['responding', '回复'],
    ['awaiting', '待答'],
    ['standby', '静待'],
    ['error', '错误'],
  ] as const)('%s → %s', (kind, label) => {
    const w = mount(VoiceStatusBadge, { props: { kind } })
    expect(w.find('.vsb').classes()).toContain(`k-${kind}`)
    expect(w.find('.vsb-label').text()).toBe(label)
  })

  it('静待时提示用唤醒词唤醒', () => {
    const w = mount(VoiceStatusBadge, { props: { kind: 'standby', wakeWord: '衍衡' } })
    expect(w.find('.vsb-label').text()).toBe('说「衍衡」唤醒')
  })

  it('聆听/通话带呼吸环，思考带三点，回复带均衡条', () => {
    expect(mount(VoiceStatusBadge, { props: { kind: 'listening' } }).find('.vsb-ring').exists()).toBe(true)
    expect(mount(VoiceStatusBadge, { props: { kind: 'call' } }).find('.vsb-ring').exists()).toBe(true)
    expect(mount(VoiceStatusBadge, { props: { kind: 'thinking' } }).findAll('.vsb-dots i')).toHaveLength(3)
    expect(mount(VoiceStatusBadge, { props: { kind: 'responding' } }).findAll('.vsb-eq i')).toHaveLength(3)
  })
})
