// @vitest-environment jsdom
/** 分组下拉：组标题、跨组选项、搜索过滤、选中回写。Grouped select: headers, options, search, selection. */
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import UiGroupedSelect from '../UiGroupedSelect.vue'

let lastWrapper: VueWrapper<any> | null = null

afterEach(async () => {
  lastWrapper?.unmount()
  lastWrapper = null
  await flushPromises()
})

const GROUPS = [
  { label: '供应商 A', options: [{ value: 'a1', label: '模型 A1' }, { value: 'a2', label: '模型 A2' }] },
  { label: '供应商 B', options: [{ value: 'b1', label: '模型 B1' }] },
]

function mountSelect(initial = '') {
  const model = ref(initial)
  const w = mount({
    components: { UiGroupedSelect },
    template: '<UiGroupedSelect v-model="model" :groups="groups" />',
    setup: () => ({ model, groups: GROUPS }),
  })
  lastWrapper = w
  return { w, model }
}

describe('UiGroupedSelect', () => {
  it('触发器回显选中项，展开后按组渲染标题与选项', async () => {
    const { w } = mountSelect('a2')
    expect(w.find('.ui-gselect-value').text()).toBe('模型 A2')

    await w.find('.ui-gselect').trigger('click')
    await flushPromises()

    const headers = [...document.querySelectorAll('.ui-gselect-group-label')].map(e => e.textContent)
    expect(headers).toEqual(['供应商 A', '供应商 B'])
    const labels = [...document.querySelectorAll('.ui-gselect-option-label')].map(e => e.textContent)
    expect(labels).toEqual(['模型 A1', '模型 A2', '模型 B1'])
  })

  it('点击选项写回 v-model 并关闭', async () => {
    const { w, model } = mountSelect('')
    await w.find('.ui-gselect').trigger('click')
    await flushPromises()

    ;(document.querySelectorAll('.ui-gselect-option')[2] as HTMLElement).click()
    await nextTick()

    expect(model.value).toBe('b1')
    expect(document.querySelector('.ui-gselect-panel')).toBeNull()
  })

  it('搜索按模型名过滤，整组无匹配时隐藏组标题', async () => {
    const { w } = mountSelect('')
    await w.find('.ui-gselect').trigger('click')
    await flushPromises()

    const input = document.querySelector('.ui-gselect-search') as HTMLInputElement
    input.value = 'B1'
    input.dispatchEvent(new Event('input'))
    await nextTick()

    expect([...document.querySelectorAll('.ui-gselect-group-label')].map(e => e.textContent))
      .toEqual(['供应商 B'])
    expect([...document.querySelectorAll('.ui-gselect-option-label')].map(e => e.textContent))
      .toEqual(['模型 B1'])
  })

  it('Esc 关闭面板', async () => {
    const { w } = mountSelect('')
    await w.find('.ui-gselect').trigger('click')
    await flushPromises()
    expect(document.querySelector('.ui-gselect-panel')).not.toBeNull()

    w.find('.ui-gselect').trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(document.querySelector('.ui-gselect-panel')).toBeNull()
  })
})
