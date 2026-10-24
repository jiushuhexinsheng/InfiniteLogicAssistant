// @vitest-environment jsdom
/** 测试连接状态点：四种状态的样式类与标题。Connection-test status dot: classes and titles. */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DetectionStatusDot from '../DetectionStatusDot.vue'

describe('DetectionStatusDot', () => {
  it.each([
    ['idle', '未测试'],
    ['testing', '测试中'],
    ['ok', '成功'],
    ['fail', '失败'],
  ] as const)('%s 状态渲染对应样式与标题', (status, label) => {
    const w = mount(DetectionStatusDot, { props: { status, detail: label } })
    const dot = w.find('.det-dot')
    expect(dot.exists()).toBe(true)
    expect(dot.classes()).toContain(`st-${status}`)
    expect(dot.attributes('title')).toContain(label)
  })

  it('detail 优先作为 title', () => {
    const w = mount(DetectionStatusDot, {
      props: { status: 'ok', detail: '上次检测：成功 · 120ms' },
    })
    expect(w.find('.det-dot').attributes('title')).toBe('上次检测：成功 · 120ms')
  })
})
