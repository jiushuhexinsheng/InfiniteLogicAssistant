// @vitest-environment jsdom
/** 获取模型弹窗：搜索、已添加禁用、添加所选后关闭。Fetched-model dialog behaviour. */
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import FetchedModelDialog from '../FetchedModelDialog.vue'

let lastWrapper: VueWrapper<any> | null = null
afterEach(async () => {
  lastWrapper?.unmount()
  lastWrapper = null
  await flushPromises()
})

function mountDialog(models = ['a', 'b'], added: string[] = ['b']) {
  const open = ref(true)
  const events: string[][] = []
  const w = mount({
    components: { FetchedModelDialog },
    template: '<FetchedModelDialog v-model="open" :models="models" :added="added" @add="v => events.push(v)" />',
    setup: () => ({ open, models, added, events }),
  })
  lastWrapper = w
  return { w, open, events }
}

describe('FetchedModelDialog', () => {
  it('显示标题与复选行，已添加项禁用', async () => {
    mountDialog()
    await nextTick()
    expect(document.body.textContent).toContain('选择要添加的模型')
    expect(document.querySelectorAll('.fm-row')).toHaveLength(2)
    const b = document.querySelectorAll<HTMLInputElement>('.fm-row input')[1]
    expect(b.disabled).toBe(true)
  })

  it('搜索过滤模型', async () => {
    mountDialog()
    await nextTick()
    const search = document.querySelector<HTMLInputElement>('.fmd-search')!
    search.value = 'a'
    search.dispatchEvent(new Event('input'))
    await nextTick()

    expect(document.querySelectorAll('.fm-row')).toHaveLength(1)
  })

  it('添加所选后回传并关闭弹窗', async () => {
    const { open, events } = mountDialog()
    await nextTick()
    const first = document.querySelector<HTMLInputElement>('.fm-row input')!
    first.checked = true
    first.dispatchEvent(new Event('change'))
    await nextTick()

    document.querySelector<HTMLElement>('.fm-add')!.click()
    await nextTick()

    expect(events).toEqual([['a']])
    expect(open.value).toBe(false)
  })
})
