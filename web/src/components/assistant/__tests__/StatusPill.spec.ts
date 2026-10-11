// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import StatusPill from '../StatusPill.vue'
import { STATE_VISUALS } from '../../../composables/useAssistantVisuals'
import { callActive } from '../../../composables/assistant/store'
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
  it('待机显示「双击开启语音」（2026-10-11：双击=电源开关）', () => {
    expect(mountPill('idle').text()).toContain('双击开启语音')
  })

  it('聆听显示状态与唤醒词', () => {
    const text = mountPill('listening').text()
    expect(text).toContain('聆听中')
    expect(text).toContain(WAKE_HINT)
  })

  /**
   * R2（计划缺口补充，台账裁决）：通话激活时 listening 胶囊必须显示「通话聆听中」——
   * spec 文案要求，且 T14 验收断言依赖它（缺了 verify:voice 通话场景恒 INCONCLUSIVE）。
   * callActive 是 store 单例，与 callMode.spec 同模式直接注入、finally 复位防泄漏。
   *
   * R2 (plan-gap supplement, ledger ruling): with a call active the listening pill must read
   * 「通话聆听中」 — required by the spec copy and relied on by T14's acceptance assertion
   * (without it verify:voice's call scenario is INCONCLUSIVE forever). `callActive` is the
   * store singleton, injected directly in the callMode.spec style and reset in `finally`
   * so it cannot leak into sibling cases.
   */
  it('通话激活时聆听态胶囊显示「通话聆听中」', () => {
    callActive.value = true
    try {
      expect(mountPill('listening').text()).toContain('通话聆听中')
    } finally {
      callActive.value = false
    }
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

  it('只有麦克风在收音的状态才显示声波条（含静待——静待保持本地侦听）', () => {
    expect(mountPill('listening').find('.sp-eq').exists()).toBe(true)
    expect(mountPill('standby').find('.sp-eq').exists()).toBe(true)
    expect(mountPill('idle').find('.sp-eq').exists()).toBe(false)
  })

  /**
   * 声波条不再走 CSS 定时动画 —— 高度随 micLevel 单例实时变化（用户需求：
   * 「根据声音收集去动」）。静音回落 4px 基线，说话时拉高。
   * The bars no longer run a CSS timer animation — heights follow the micLevel
   * singleton in real time (the "move with the captured sound" requirement). Silence
   * rests on the 4px baseline; speech stretches them.
   */
  it('声波条高度随麦克风电平起伏', async () => {
    const { micLevel, resetMicLevel } = await import('../../../composables/assistant/micLevel')
    const heightsOf = (w: ReturnType<typeof mountPill>) =>
      w.find('.sp-eq').findAll('i').map(b => (b.element as HTMLElement).style.height)
    try {
      resetMicLevel()
      const quiet = mountPill('listening')
      expect(heightsOf(quiet)).toEqual(['4px', '4px', '4px', '4px'])
      quiet.unmount()

      micLevel.value = 1
      const loud = mountPill('listening')
      expect(heightsOf(loud)).toEqual(['14px', '10px', '13px', '9px'])
    } finally {
      resetMicLevel()
    }
  })
})
