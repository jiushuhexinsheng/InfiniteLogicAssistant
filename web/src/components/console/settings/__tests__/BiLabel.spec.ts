// @vitest-environment jsdom
/** 双语标签：inline 同行、stack 英文换行、英文与中文相同时省略。 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BiLabel from '../BiLabel.vue'

describe('BiLabel', () => {
  it('inline 布局：中英文同一行', () => {
    const w = mount(BiLabel, { props: { zh: '保存', en: 'Save' } })
    expect(w.find('.bi-label').classes()).not.toContain('stack')
    expect(w.find('.bi-en').text()).toBe('Save')
  })

  it('stack 布局：英文在下一行', () => {
    const w = mount(BiLabel, { props: { zh: '保存', en: 'Save', layout: 'stack' } })
    expect(w.find('.bi-label').classes()).toContain('stack')
    expect(w.find('.bi-en').text()).toBe('Save')
  })

  it('stack 下英文与中文相同则省略英文行', () => {
    const w = mount(BiLabel, { props: { zh: 'API', en: 'API', layout: 'stack' } })
    expect(w.find('.bi-en').exists()).toBe(false)
  })
})
