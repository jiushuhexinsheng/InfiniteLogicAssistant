// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MiniPlayer from '../MiniPlayer.vue'
import { STATE_VISUALS } from '../../../composables/useAssistantVisuals'
import type { AsstState, ChatMessage } from '../../../composables/useAssistant'

/** 最小完整消息（id/blocks/timestamp 为必填）。Minimal complete message. */
function msg(text: string, role: ChatMessage['role'] = 'assistant'): ChatMessage {
  return { id: 'm1', role, text, blocks: [], timestamp: 0 }
}

/**
 * 2026-10-07「我说话没有反应」修复的第二落点：迷你条文本优先级。
 * 原实现 partialText → lastMsg → statusLine —— 有历史消息时 statusLine 永远轮不到，
 * 通话漏斗 miss 的可见反馈（statusLine）在最常见的场景（会话里已有对话）下不可见。
 * 修后 partialText → statusLine → lastMsg：miss 反馈插到历史消息之前。
 *
 * Second landing point of the 2026-10-07 "I speak and nothing happens" fix: mini-bar
 * text priority. The old order (partialText → lastMsg → statusLine) meant statusLine
 * never rendered once any history existed — funnel-miss feedback was invisible in the
 * most common case. New order: partialText → statusLine → lastMsg.
 */
function mountMini(over: Partial<{
  expanded: boolean
  state: AsstState
  messages: ChatMessage[]
  partialText: string
  statusLine: string
  miniDismiss: boolean
}> = {}) {
  const state = over.state ?? 'listening'
  return mount(MiniPlayer, {
    props: {
      expanded: false,
      state,
      visual: STATE_VISUALS[state],
      messages: [],
      partialText: '',
      statusLine: '',
      miniDismiss: false,
      ...over,
    },
  })
}

describe('MiniPlayer 文本优先级', () => {
  it('statusLine 非空时优先于最后一条消息（miss 反馈必须可见）', () => {
    const w = mountMini({
      statusLine: '未识别为指令（旁人/背景）',
      messages: [msg('旧回复')],
    })
    expect(w.find('.mini-content').text()).toBe('未识别为指令（旁人/背景）')
  })

  it('statusLine 为空 → 回退最后一条消息', () => {
    const w = mountMini({ messages: [msg('旧回复')] })
    expect(w.find('.mini-content').text()).toBe('旧回复')
  })

  it('录音中的 partialText 仍最高优先（高于 statusLine）', () => {
    const w = mountMini({
      state: 'recording',
      partialText: '正在说…',
      statusLine: '窗口未聚焦，语音未处理',
      messages: [msg('旧回复')],
    })
    expect(w.find('.mini-content').text()).toBe('正在说…')
  })

  it('非活跃态且无消息 → 迷你条不渲染', () => {
    const w = mountMini({ state: 'done' })
    expect(w.find('.mini-player').exists()).toBe(false)
  })
})
