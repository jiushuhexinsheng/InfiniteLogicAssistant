// @vitest-environment jsdom
/** 供应商列表：展示、编辑、删除确认、设为当前。Provider list: render, edit, delete confirm, activate. */
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ProviderList from '../ProviderList.vue'

const PROVIDERS = [
  { id: 'p1', name: 'p1', protocol: 'openai', endpoint: 'https://a', keySet: true, active: true, modelCount: 2 },
  { id: 'p2', name: 'p2', protocol: 'anthropic', endpoint: 'https://b', keySet: false, active: false, modelCount: 1 },
]

function mountList() {
  return mount(ProviderList, { props: { providers: PROVIDERS } })
}

describe('ProviderList', () => {
  it('渲染两行：名称/协议/地址/Key/当前徽章/模型数', () => {
    const w = mountList()
    const rows = w.findAll('.pr-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('openai')
    expect(rows[0].text()).toContain('https://a')
    expect(rows[0].text()).toContain('当前')
    expect(rows[0].text()).toContain('2')
    expect(rows[1].text()).toContain('Key 未设置')
  })

  it('点行进入编辑', async () => {
    const w = mountList()
    await w.findAll('.pr-row')[1].trigger('click')
    expect(w.emitted('edit')?.[0]).toEqual(['p2'])
  })

  it('删除先弹确认，确认后才发 remove', async () => {
    const w = mountList()
    await w.findAll('.pr-del')[1].trigger('click')
    expect(w.emitted('remove')).toBeUndefined()
    expect(document.body.textContent).toContain('删除供应商「p2」')

    const confirm = [...document.querySelectorAll('.ui-btn')]
      .find(b => b.textContent?.includes('删除')) as HTMLElement
    confirm.click()
    await flushPromises()

    expect(w.emitted('remove')?.[0]).toEqual(['p2'])
  })

  it('非当前行显示「设为当前」并发 activate', async () => {
    const w = mountList()
    const activate = w.findAll('.pr-activate')[0]
    await activate.trigger('click')
    expect(w.emitted('activate')?.[0]).toEqual(['p2'])
    expect(w.findAll('.pr-row')[0].text()).not.toContain('设为当前')
  })
})
