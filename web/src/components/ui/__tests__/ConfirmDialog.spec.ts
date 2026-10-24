// @vitest-environment jsdom
/** 通用确认框：取消/确认各自 emit 并关闭。Generic confirm dialog: cancel/confirm emit and close. */
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import ConfirmDialog from '../ConfirmDialog.vue'

let lastWrapper: VueWrapper<any> | null = null

afterEach(async () => {
  lastWrapper?.unmount()
  lastWrapper = null
  await flushPromises()
})

function mountDialog() {
  const open = ref(true)
  const events: string[] = []
  const w = mount({
    components: { ConfirmDialog },
    template: `<ConfirmDialog v-model="open" title="删除供应商" message="此操作不可撤销"
      @confirm="events.push('confirm')" @cancel="events.push('cancel')" />`,
    setup: () => ({ open, events }),
  })
  lastWrapper = w
  return { w, open, events }
}

describe('ConfirmDialog', () => {
  it('显示标题与正文', async () => {
    mountDialog()
    await nextTick()
    expect(document.body.textContent).toContain('删除供应商')
    expect(document.body.textContent).toContain('此操作不可撤销')
  })

  it('取消：emit cancel 并关闭', async () => {
    const { open, events } = mountDialog()
    await nextTick()
    const buttons = [...document.querySelectorAll('.ui-btn')] as HTMLElement[]
    const cancel = buttons.find(b => b.textContent?.includes('取消'))!
    cancel.click()
    await nextTick()
    expect(events).toEqual(['cancel'])
    expect(open.value).toBe(false)
  })

  it('确认：emit confirm 并关闭', async () => {
    const { open, events } = mountDialog()
    await nextTick()
    const buttons = [...document.querySelectorAll('.ui-btn')] as HTMLElement[]
    const confirm = buttons.find(b => b.textContent?.includes('确认'))!
    confirm.click()
    await nextTick()
    expect(events).toEqual(['confirm'])
    expect(open.value).toBe(false)
  })
})
