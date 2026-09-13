// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import StatusPill from '../StatusPill.vue'
import { STATE_VISUALS } from '../../../composables/useAssistantVisuals'
import type { AsstState } from '../../../composables/useAssistant'

const WAKE_HINT = '「衍衡」或「洛吉斯」'

/** 按真实状态视觉挂载胶囊。Mount the pill against the real state visuals. */
function mountPill(state: AsstState, over: Record<string, unknown> = {}) {
  return mount(StatusPill, {
    props: {
      visual: STATE_VISUALS[state],
      state,
      wakeHint: WAKE_HINT,
      visible: true,
      side: 'right' as const,
      ...over,
    },
  })
}

/**
 * 胶囊模板顶端带注释，组件因此是多根节点，挂载包装器的 element 是外层容器。
 * 状态类与 CSS 变量都落在 .status-pill 上，所以统一从它读取。
 *
 * The template opens with a comment, so the component has multiple root nodes and the mount
 * wrapper's `element` is the outer container. The state classes and the CSS variables land on
 * `.status-pill`, so read everything through it.
 */
function pillOf(w: VueWrapper) {
  return w.find<HTMLElement>('.status-pill')
}

/**
 * 胶囊要说的就是「现在能做什么」，所以每个状态都得有字。
 * The pill exists to say what the user can do right now, so every state must render copy.
 */
describe('StatusPill 状态文案', () => {
  it('待机显示「双击唤醒」', () => {
    expect(mountPill('idle').text()).toContain('双击唤醒')
  })

  it('聆听显示状态与唤醒词', () => {
    const text = mountPill('listening').text()
    expect(text).toContain('聆听中')
    expect(text).toContain(WAKE_HINT)
  })

  /**
   * responding 在共享视觉里 label 为空（面板头不需要这个词），胶囊没有别的载体，
   * 所以必须兜底，否则这一段整块是空白。
   *
   * `responding` ships an empty label in the shared visuals (the panel header does not need the
   * word). The pill has no other surface, so it must fall back or render nothing at all.
   */
  it('回复中（共享 label 为空）有兜底文案', () => {
    expect(mountPill('responding').text()).toContain('回复中')
  })
})

describe('StatusPill 外观与侧向', () => {
  it('状态色注入 CSS 变量供描边/圆点共用', () => {
    const style = pillOf(mountPill('listening')).element.style
    expect(style.getPropertyValue('--sp-color')).toBe(STATE_VISUALS.listening.color)
    expect(style.getPropertyValue('--sp-border')).toContain('rgba(')
  })

  it('球在右侧时尖角朝右，球在左侧时朝左', () => {
    expect(pillOf(mountPill('idle', { side: 'right' })).classes()).toContain('tail-right')
    expect(pillOf(mountPill('idle', { side: 'left' })).classes()).toContain('tail-left')
  })

  it('面板展开（visible=false）时淡出让位', () => {
    expect(pillOf(mountPill('idle', { visible: false })).classes()).toContain('hidden')
    expect(pillOf(mountPill('idle')).classes()).not.toContain('hidden')
  })

  it('只有麦克风在收音的状态才显示声波条', () => {
    expect(mountPill('listening').find('.sp-eq').exists()).toBe(true)
    expect(mountPill('idle').find('.sp-eq').exists()).toBe(false)
  })
})
