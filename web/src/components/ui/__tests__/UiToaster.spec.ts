// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { notify } from '../../../composables/useToast'
import UiToaster from '../UiToaster.vue'

/**
 * UiToaster 全局通知浮层（Teleport 到 body）。
 * UiToaster global notification overlay (teleported to body).
 *
 * 注意：Teleport 的目标是 document.body，故必须 attachTo + unmount 正规清理；
 * 直接清空 document.body.innerHTML 会抹掉 Teleport 的锚点，导致 patch 时
 * insertBefore(null) 崩溃。
 *
 * Note: the Teleport target is document.body, so use attachTo + unmount for cleanup.
 * Wiping document.body.innerHTML removes the Teleport anchor and makes patching
 * crash with insertBefore(null).
 */
describe('UiToaster', () => {
  let wrapper: VueWrapper

  beforeEach(() => { notify.clear() })
  afterEach(() => {
    notify.clear()
    wrapper?.unmount()
  })

  /** 无通知时不渲染任何节点。Renders nothing when the queue is empty. */
  it('无通知时不渲染浮层', () => {
    wrapper = mount(UiToaster, { attachTo: document.body })
    expect(document.body.querySelector('.ui-toaster')).toBeNull()
  })

  /** 有通知时渲染文案，并按类型加 class（决定色调）。Renders the text and a kind class (which drives the tone). */
  it('有通知时渲染文案与类型 class', async () => {
    wrapper = mount(UiToaster, { attachTo: document.body })
    notify.err('保存失败：连接超时')
    await nextTick()
    const el = document.body.querySelector('.ui-toast')
    expect(el?.textContent).toBe('保存失败：连接超时')
    expect(el?.classList.contains('k-err')).toBe(true)
  })

  /** 多条通知并存，各自渲染。Multiple notices coexist and each renders. */
  it('多条通知并存', async () => {
    wrapper = mount(UiToaster, { attachTo: document.body })
    notify.ok('已保存')
    notify.warn('需重启生效')
    await nextTick()
    expect(document.body.querySelectorAll('.ui-toast')).toHaveLength(2)
  })

  /** 点击条目立即移除（不等自动消失）。Clicking an entry dismisses it immediately. */
  it('点击条目立即移除', async () => {
    wrapper = mount(UiToaster, { attachTo: document.body })
    notify.ok('已保存')
    await nextTick()
    ;(document.body.querySelector('.ui-toast') as HTMLElement).click()
    await nextTick()
    expect(document.body.querySelector('.ui-toast')).toBeNull()
  })
})
