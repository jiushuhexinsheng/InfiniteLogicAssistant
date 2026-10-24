// @vitest-environment jsdom
/** 拉取结果列表：勾选、已添加禁用、全选/反选、添加所选。Fetched list: pick, disabled added, select-all/invert, add. */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import FetchedModelList from '../FetchedModelList.vue'

function mountList(models = ['m1', 'm2', 'm3'], added: string[] = ['m2']) {
  return mount(FetchedModelList, { props: { models, added } })
}

describe('FetchedModelList', () => {
  it('已添加项禁用并标注', () => {
    const w = mountList()
    const rows = w.findAll('.fm-row')
    expect(rows).toHaveLength(3)
    const m2 = rows[1]
    expect(m2.text()).toContain('已添加')
    expect((m2.find('input').element as HTMLInputElement).disabled).toBe(true)
  })

  it('勾选两项后「添加所选」只发未添加项', async () => {
    const w = mountList()
    await w.findAll('.fm-row input')[0].setValue(true)
    await w.findAll('.fm-row input')[2].setValue(true)

    await w.find('.fm-add').trigger('click')

    expect(w.emitted('add')?.[0]?.[0]).toEqual(['m1', 'm3'])
  })

  it('全选只覆盖未添加项，反选切换未添加项', async () => {
    const w = mountList(['m1', 'm2', 'm3'], ['m2'])
    await w.find('.fm-all').trigger('click')
    const checked = w.findAll('.fm-row input').map(i => (i.element as HTMLInputElement).checked)
    expect(checked).toEqual([true, false, true])

    await w.find('.fm-invert').trigger('click')
    const inverted = w.findAll('.fm-row input').map(i => (i.element as HTMLInputElement).checked)
    expect(inverted).toEqual([false, false, false])
  })
})
