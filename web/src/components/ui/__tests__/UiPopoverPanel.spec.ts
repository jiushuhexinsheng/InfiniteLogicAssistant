// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'

import UiPopoverPanel from '../UiPopoverPanel.vue'

/**
 * UiPopoverPanel（UiSelect / UiCombobox 共享的锚定弹层外壳）。
 *
 * 为什么单测它：两个消费者的弹层样式过去是**逐条镜像**的，抽取后弹层只有这一份实现
 * —— 它回归了，两个下拉一起回归。这里钉住的是外壳自己的契约：选项行怎么渲染、
 * `listbox` 语义开在哪、行事件怎么发、哪种时机提交选中。两个消费者的领域逻辑
 * （选项从哪来、过滤、键盘如何解释）在各自的 spec 里验。
 *
 * Why this spec exists: the two consumers' panel styles used to be mirrored line-by-line;
 * after extraction this is the single implementation — if it regresses, both dropdowns
 * regress. It pins the shell's own contract: how rows render, where listbox semantics
 * appear, which events rows emit, and when a row commits. The consumers' domain logic
 * (option sources, filtering, key interpretation) is covered by their own specs.
 */

/** 最近挂载的 wrapper：统一由 Vue 卸载（Teleport 挂在 body，禁止粗暴 innerHTML 清场）。
 *  Latest mounted wrapper: unmounted by Vue (Teleport targets body; never wipe with innerHTML). */
let lastWrapper: VueWrapper<any> | null = null

afterEach(async () => {
  lastWrapper?.unmount()
  lastWrapper = null
  await flushPromises()
})

/** 测试用选项行。The option rows used by the tests. */
const ITEMS = [
  { value: 'a', label: '选项A' },
  { value: 'b', label: '选项B' },
  { value: 'c', label: '选项C' },
]

/** body 下的弹层根元素（面板是 Teleport 出来的，必须在 document 上查）。
 *  The panel root under body (it is teleported, so it must be queried on the document). */
function menu(): HTMLElement {
  return document.querySelector('.ui-select-menu') as HTMLElement
}

/** body 下的选项行。The panel rows under body. */
function rows(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>('.ui-select-option')]
}

/**
 * 挂一个弹层。Mount a panel.
 * @param props 覆盖的 props。Prop overrides.
 * @returns wrapper（事件断言用）。The wrapper (for event assertions).
 */
function setup(props: Record<string, unknown> = {}) {
  const w = mount(UiPopoverPanel, { props: { listId: 'p1', items: ITEMS, ...props } })
  lastWrapper = w
  return w
}

/**
 * 在行上派发一个可取消的鼠标事件，返回该事件对象（用来断言 `defaultPrevented`）。
 * Dispatch a cancelable mouse event on a row and return it (to assert `defaultPrevented`).
 *
 * @param el 目标元素。Target element.
 * @param type 事件类型。Event type.
 * @returns 派发出去的事件。The dispatched event.
 */
function fire(el: HTMLElement, type: string): MouseEvent {
  const e = new MouseEvent(type, { bubbles: true, cancelable: true })
  el.dispatchEvent(e)
  return e
}

describe('UiPopoverPanel（锚定弹层外壳）', () => {
  /** Teleport 到 body、按 items 渲染、行 id 由 listId 派生。 */
  it('Teleport 到 body 并按 items 渲染选项行', () => {
    setup()
    expect(menu(), '弹层应挂到 body 下').toBeTruthy()
    expect(menu().id).toBe('p1')
    const r = rows()
    expect(r.length).toBe(3)
    expect(r[0].id).toBe('p1-0')
    expect(r[2].querySelector('.ui-select-option-label')!.textContent).toBe('选项C')
  })

  /** listbox 语义：role / aria-selected / data-value 全开（UiSelect 的用法）。 */
  it('listbox 开启时输出 role / aria-selected / data-value', () => {
    setup({ listbox: true, selected: 'b' })
    expect(menu().getAttribute('role')).toBe('listbox')
    const r = rows()
    expect(r[0].getAttribute('role')).toBe('option')
    expect(r[1].getAttribute('data-value')).toBe('b')
    expect(r[1].getAttribute('aria-selected')).toBe('true')
    expect(r[0].getAttribute('aria-selected')).toBe('false')
  })

  /** 建议层语义（UiCombobox 的用法）：这三样属性一个都不该出现。 */
  it('listbox 关闭时不输出 role / aria-selected / data-value', () => {
    setup({ selected: 'b' })
    expect(menu().hasAttribute('role')).toBe(false)
    const r = rows()[0]
    expect(r.hasAttribute('role')).toBe(false)
    expect(r.hasAttribute('data-value')).toBe(false)
    expect(r.hasAttribute('aria-selected')).toBe(false)
  })

  /** 选中行打勾并带 .sel，键盘活动行带 .on。 */
  it('标记选中行（打勾）与键盘活动行', () => {
    setup({ selected: 'c', activeIndex: 1 })
    const r = rows()
    expect(r[2].classList.contains('sel')).toBe(true)
    expect(r[2].querySelector('.ui-select-check')).toBeTruthy()
    expect(r[0].querySelector('.ui-select-check')).toBeNull()
    expect(r[1].classList.contains('on')).toBe(true)
  })

  /** 翻转标记与定位样式透传到弹层根元素。 */
  it('flipUp 与 panelStyle 透传到弹层', () => {
    setup({ flipUp: true, panelStyle: { left: '12px', bottom: '34px' } })
    expect(menu().classList.contains('up')).toBe(true)
    expect(menu().style.left).toBe('12px')
    expect(menu().style.bottom).toBe('34px')
  })

  /** 行事件：click 默认提交行索引，mousemove 报告悬停索引（是否同步活动项由调用方决定）。 */
  it('click 默认提交行索引，mousemove 报告悬停索引', () => {
    const w = setup()
    fire(rows()[1], 'mousemove')
    fire(rows()[2], 'click')
    expect(w.emitted('hover')).toEqual([[1]])
    expect(w.emitted('pick')).toEqual([[2]])
  })

  /**
   * pickOn='mousedown'：mousedown 提交**且阻止默认行为**（否则输入框先失焦、面板先关，
   * 选中落不下来）；此时 click 不再提交，避免同一次点击提交两回。
   */
  it('pickOn=mousedown 时由 mousedown 提交并阻止默认，click 不重复提交', () => {
    const w = setup({ pickOn: 'mousedown' })
    expect(fire(rows()[1], 'mousedown').defaultPrevented).toBe(true)
    expect(w.emitted('pick')).toEqual([[1]])
    fire(rows()[2], 'click')
    expect(w.emitted('pick')).toEqual([[1]])   // 仍只有一次
  })

  /** pickOn='click'（默认）时 mousedown 不拦默认、不提交（与抽取前的 UiSelect 行逐字一致）。 */
  it('pickOn=click 时 mousedown 不拦默认也不提交', () => {
    const w = setup()
    expect(fire(rows()[0], 'mousedown').defaultPrevented).toBe(false)
    expect(w.emitted('pick')).toBeUndefined()
  })

  /** 空选项渲染空态行（实参里只有 UiSelect 会走到；UiCombobox 无建议则不打开面板）。 */
  it('items 为空时渲染空态行', () => {
    setup({ items: [] })
    expect(document.querySelector('.ui-select-empty')!.textContent).toBe('无选项')
    expect(rows().length).toBe(0)
  })
})
