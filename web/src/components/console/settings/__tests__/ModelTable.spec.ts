// @vitest-environment jsdom
/** 模型表格：逐行编辑、增删、去重与空行过滤。Model table: per-row edit/add/remove, dedupe, empty filtering. */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ModelTable from '../ModelTable.vue'

function mountTable(models = ['a', 'b', 'c'], options: string[] = []) {
  return mount(ModelTable, { props: { models, options } })
}

function lastEmitted(w: ReturnType<typeof mountTable>): string[] {
  const events = w.emitted('update:models') as unknown[][] | undefined
  return (events?.at(-1)?.[0] as string[]) ?? []
}

describe('ModelTable', () => {
  it('渲染每行模型，编辑一行即发出新数组', async () => {
    const w = mountTable()
    const inputs = w.findAll('input')
    expect(inputs).toHaveLength(3)

    await inputs[1].setValue('b2')

    expect(lastEmitted(w)).toEqual(['a', 'b2', 'c'])
  })

  it('删除一行', async () => {
    const w = mountTable()
    await w.findAll('.mt-del')[1].trigger('click')
    expect(lastEmitted(w)).toEqual(['a', 'c'])
  })

  it('添加空行：可见行 +1，填充后进入输出', async () => {
    const w = mountTable()
    await w.find('.mt-add').trigger('click')
    expect(w.findAll('input')).toHaveLength(4)

    await w.findAll('input')[3].setValue('d')

    expect(lastEmitted(w)).toEqual(['a', 'b', 'c', 'd'])
  })

  it('重复值去重、空行不进入输出', async () => {
    const w = mountTable()
    const inputs = w.findAll('input')

    await inputs[2].setValue('a')
    expect(lastEmitted(w)).toEqual(['a', 'b'])

    await inputs[1].setValue('   ')
    expect(lastEmitted(w)).toEqual(['a'])
  })
})
