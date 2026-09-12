// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import UiErrorNote from '../UiErrorNote.vue'

/** UiErrorNote 内联错误提示原语。UiErrorNote inline error-note primitive. */
describe('UiErrorNote', () => {
  /** 有错误文案时渲染出来。Renders the message when one is present. */
  it('有错误时渲染文案', () => {
    const w = mount(UiErrorNote, { props: { error: '加载失败：连接超时' } })
    expect(w.find('.ui-errnote').exists()).toBe(true)
    expect(w.text()).toBe('加载失败：连接超时')
  })

  /** 空值一律不渲染，避免留下空边框。Empty values render nothing, avoiding an empty box. */
  it('错误为空时不渲染', () => {
    for (const empty of [null, undefined, '']) {
      const w = mount(UiErrorNote, { props: { error: empty } })
      expect(w.find('.ui-errnote').exists()).toBe(false)
    }
  })
})
