// @vitest-environment jsdom
/** 概览能力卡：编号、双语名、状态色、点击跳转。Voice status tile behaviour. */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import VoiceStatusTile from '../VoiceStatusTile.vue'

describe('VoiceStatusTile', () => {
  it('渲染编号、中英文名与模式/详情', () => {
    const w = mount(VoiceStatusTile, {
      props: { order: 3, zh: 'KWS', en: 'Keyword', detail: '本地 · 3.3M', tone: 'ok', mode: '本地' },
    })
    expect(w.find('.vt-order').text()).toBe('3')
    expect(w.text()).toContain('KWS')
    expect(w.text()).toContain('Keyword')
    expect(w.text()).toContain('本地 · 3.3M')
    expect(w.find('.voice-tile').classes()).toContain('ok')
  })

  it('点击发出 select', async () => {
    const w = mount(VoiceStatusTile, {
      props: { order: 1, zh: '麦克风', en: 'Mic', detail: '浏览器输入', tone: 'ok' },
    })
    await w.find('.voice-tile').trigger('click')
    expect(w.emitted('select')).toHaveLength(1)
  })

  it('err 状态带错误样式', () => {
    const w = mount(VoiceStatusTile, {
      props: { order: 4, zh: 'ASR', en: 'Speech', detail: '未就绪', tone: 'err' },
    })
    expect(w.find('.voice-tile').classes()).toContain('err')
  })
})
