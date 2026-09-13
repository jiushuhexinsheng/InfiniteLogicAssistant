import { beforeEach, describe, expect, it } from 'vitest'
import { assistantMode, loadStoredMode, setAssistantMode } from '../store'

/** 助手模式：显式切换 + localStorage 持久化。
 *  Assistant mode: explicit switching with localStorage persistence. */
describe('assistantMode', () => {
  beforeEach(() => {
    localStorage.clear()
    assistantMode.value = 'chat'
  })

  /** 缺省为对话模式（不询问完成、不改行为）。Defaults to chat mode. */
  it('缺省为 chat', () => {
    localStorage.clear()
    expect(loadStoredMode()).toBe('chat')
  })

  /** 切换写回 localStorage。Switching persists to localStorage. */
  it('切换持久化', () => {
    setAssistantMode('task')
    expect(assistantMode.value).toBe('task')
    expect(localStorage.getItem('xluo.assistantMode')).toBe('task')
  })

  /** 非法持久化值回退 chat（防止手改 localStorage 造成未知模式）。
   *  An invalid persisted value falls back to chat. */
  it('非法持久化值回退 chat', () => {
    localStorage.setItem('xluo.assistantMode', '胡说')
    expect(loadStoredMode()).toBe('chat')
  })

  /** 切回对话模式也要正确持久化。Switching back to chat persists too. */
  it('切回对话模式', () => {
    setAssistantMode('task')
    setAssistantMode('chat')
    expect(assistantMode.value).toBe('chat')
    expect(localStorage.getItem('xluo.assistantMode')).toBe('chat')
  })
})
