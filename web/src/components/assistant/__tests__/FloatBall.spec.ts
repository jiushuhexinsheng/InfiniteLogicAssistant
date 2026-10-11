// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import FloatBall from '../FloatBall.vue'
import { STATE_VISUALS } from '../../../composables/useAssistantVisuals'
import type { AsstState } from '../../../composables/useAssistant'

/** 挂载悬浮球（idle 待机态，最小 props）。Mount the float ball (idle state, minimal props). */
function mountBall(state: AsstState = 'idle'): VueWrapper {
  return mount(FloatBall, {
    props: {
      pos: { x: 100, y: 100 },
      state,
      visual: STATE_VISUALS[state],
      messageDot: false,
      expanded: false,
      wakeEnabled: false,
    },
  })
}

/**
 * 用原生 MouseEvent 走指针按下/移动/松开序列。jsdom 对 PointerEvent 的支持不保证，
 * 而组件的拖拽监听只读 clientX/clientY —— MouseEvent 完全够用，且不依赖 test-utils
 * 对事件构造器的映射。
 *
 * Drive pointerdown/move/up with plain MouseEvents: jsdom's PointerEvent support is not
 * guaranteed, and the drag listeners only read clientX/clientY — a MouseEvent suffices and
 * avoids depending on test-utils' event-constructor mapping.
 */
function fire(el: Element | Document, type: string, init: MouseEventInit = {}): void {
  el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, ...init }))
}

function dragPress(w: VueWrapper, fromX: number, dx: number): void {
  const ball = w.find('.float-trigger').element
  fire(ball, 'pointerdown', { clientX: fromX, clientY: 100, pointerId: 1 })
  fire(document, 'pointermove', { clientX: fromX + dx, clientY: 100 })
  fire(document, 'pointerup', { clientX: fromX + dx, clientY: 100 })
}

afterEach(() => {
  vi.useRealTimers()
})

/**
 * 单击/双击**分离**（2026-10-11 用户需求）：单击延迟 300ms 发射，原生 dblclick 先到
 * 并取消待发单击 —— 双击只开通话、单击只开面板，互不夹带。判定时机仍交给浏览器/系统
 * （沿用 2026-10-05 根因修复：不自设双击时间窗）。
 *
 * Single/double click **separation** (2026-10-11 user requirement): a single click emits
 * after a 300ms defer; the native dblclick arrives first and cancels the pending single —
 * a double toggles the call only, a single toggles the panel only. The verdict still
 * belongs to the browser/OS (keeping the 2026-10-05 root-cause fix: no hand-rolled
 * double-click window).
 */
describe('FloatBall 单击/双击判定', () => {
  it('单击延迟 300ms 发射（给 dblclick 先到的机会）', async () => {
    vi.useFakeTimers()
    const w = mountBall()
    await w.find('.float-trigger').trigger('click')
    expect(w.emitted('click')).toBeUndefined()   // 窗口内未发 —— 等 dblclick
    vi.advanceTimersByTime(300)
    expect(w.emitted('click')).toHaveLength(1)
  })

  it('原生 dblclick 触发 dblclick 且取消待发单击 —— 双击不夹带单击', async () => {
    vi.useFakeTimers()
    const w = mountBall()
    await w.find('.float-trigger').trigger('click')     // 第一击：待发
    await w.find('.float-trigger').trigger('click')     // 第二击：重排（仍只有一份）
    await w.find('.float-trigger').trigger('dblclick')  // 取消待发 + 发 dblclick
    vi.advanceTimersByTime(1000)
    expect(w.emitted('dblclick')).toHaveLength(1)
    expect(w.emitted('click')).toBeUndefined()          // 单击被取消，面板不闪
  })

  it('按下期间位移超过拖拽阈值 → 该击不算单击', async () => {
    vi.useFakeTimers()
    const w = mountBall()
    dragPress(w, 100, 8)   // 8px > 6px 阈值：视为拖球
    await w.find('.float-trigger').trigger('click')
    vi.advanceTimersByTime(1000)
    expect(w.emitted('click')).toBeUndefined()
  })

  it('双击中任一击是拖拽 → 整次双击作废（拖球不得顺带开通话），也不发射单击', async () => {
    vi.useFakeTimers()
    const w = mountBall()
    dragPress(w, 100, 8)   // 第一击：拖拽（dragging 置位）
    await w.find('.float-trigger').trigger('click')  // 第二击：被拖拽吞掉分支收下（不排单击）
    await w.find('.float-trigger').trigger('dblclick')
    vi.advanceTimersByTime(1000)
    expect(w.emitted('dblclick')).toBeUndefined()
    expect(w.emitted('click')).toBeUndefined()        // 拖球序列整体不产生任何点击
  })

  it('双击落在语音徽章上不冒泡到球（徽章只管唤醒开关）', async () => {
    const w = mountBall()
    await w.find('.ball-mic').trigger('dblclick')
    expect(w.emitted('dblclick')).toBeUndefined()
  })
})
