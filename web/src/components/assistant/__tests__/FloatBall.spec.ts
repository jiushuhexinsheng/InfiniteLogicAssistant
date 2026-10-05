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
 * 双击判定回归（2026-10-05「无法触发」根因）：旧实现用自设 250ms 定时器仲裁单/双击，
 * 窗口低于 Windows 系统双击速度（默认约 500ms）——自然手速的第二击落在窗口外，被拆成
 * 两次单击，dblclick 永不发出，双击开通话静默失败（audit 零 call-start、唤醒链不停）。
 * 修复改为监听原生 dblclick，判定交给浏览器/系统。
 *
 * Double-click arbitration regression (root cause of the 2026-10-05 "无法触发" report):
 * the old implementation arbitrated single vs double with a hand-rolled 250ms timer —
 * below Windows' default double-click speed (~500ms). A natural-speed second click landed
 * outside the window, got split into two single clicks, and dblclick never fired: entering
 * call mode silently did nothing (zero call-start in the audit, wake chain untouched).
 * The fix listens for the native dblclick instead and leaves the verdict to the browser/OS.
 */
describe('FloatBall 单击/双击判定', () => {
  it('单击立即触发 click（不再延迟 250ms 等双击仲裁）', async () => {
    const w = mountBall()
    await w.find('.float-trigger').trigger('click')
    expect(w.emitted('click')).toHaveLength(1)
  })

  it('原生 dblclick 触发 dblclick —— 不受自设时间窗限制', async () => {
    const w = mountBall()
    // 间隔远超旧 250ms 窗口的两击（浏览器仍会把它们判成双击：系统窗口约 500ms）。
    await w.find('.float-trigger').trigger('click')
    vi.useFakeTimers()
    vi.advanceTimersByTime(400)
    await w.find('.float-trigger').trigger('click')
    await w.find('.float-trigger').trigger('dblclick')
    expect(w.emitted('dblclick')).toHaveLength(1)
    // 双击的两次单击也各算一次（调用方各自 toggle，净效果中性）。
    expect(w.emitted('click')).toHaveLength(2)
  })

  it('按下期间位移超过拖拽阈值 → 该击不算单击', async () => {
    const w = mountBall()
    dragPress(w, 100, 8)   // 8px > 6px 阈值：视为拖球
    await w.find('.float-trigger').trigger('click')
    expect(w.emitted('click')).toBeUndefined()
  })

  it('双击中任一击是拖拽 → 整次双击作废（拖球不得顺带开通话）', async () => {
    const w = mountBall()
    dragPress(w, 100, 8)   // 第一击：拖拽
    await w.find('.float-trigger').trigger('click')  // 第二击：干净点击
    await w.find('.float-trigger').trigger('dblclick')
    expect(w.emitted('dblclick')).toBeUndefined()
  })

  it('双击落在语音徽章上不冒泡到球（徽章只管唤醒开关）', async () => {
    const w = mountBall()
    await w.find('.ball-mic').trigger('dblclick')
    expect(w.emitted('dblclick')).toBeUndefined()
  })
})
