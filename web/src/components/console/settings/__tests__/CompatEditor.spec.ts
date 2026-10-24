// @vitest-environment jsdom
/** 兼容编辑：键为可输可选 combobox，选中内置键自动带值；手输键保留值；增删行。 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CompatEditor from '../CompatEditor.vue'

function lastEntries(w: ReturnType<typeof mountCompat>): Array<[string, string]> {
  const events = w.emitted('update') as unknown[][] | undefined
  return (events?.at(-1)?.[0] as Array<[string, string]>) ?? []
}

function mountCompat(entries: Array<[string, string]> = [['auth_header', 'custom']]) {
  return mount(CompatEditor, { props: { entries } })
}

describe('CompatEditor', () => {
  it('不再渲染快捷 chip', () => {
    const w = mountCompat()
    expect(w.find('.cs-compat-chip').exists()).toBe(false)
    expect(w.text()).not.toContain('音频 data-URL')
  })

  it('选中内置键自动填默认值', async () => {
    const w = mountCompat([['', '']])
    const keyInput = w.findAll('.cr-row input')[0]
    await keyInput.setValue('auth_header')

    expect(lastEntries(w)).toEqual([['auth_header', 'api-key']])
  })

  it('手输自定义键保留原值', async () => {
    const w = mountCompat([['custom', 'keep']])
    const keyInput = w.findAll('.cr-row input')[0]
    await keyInput.setValue('another')

    expect(lastEntries(w)).toEqual([['another', 'keep']])
  })

  it('删除一行与新增兼容键', async () => {
    const w = mountCompat([['a', '1'], ['b', '2']])
    await w.findAll('.cr-del')[0].trigger('click')
    expect(lastEntries(w)).toEqual([['b', '2']])

    await w.find('.cr-add').trigger('click')
    expect(lastEntries(w)).toHaveLength(2)
  })
})
