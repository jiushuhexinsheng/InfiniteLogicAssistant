import { describe, it, expect, beforeEach } from 'vitest'
import {
  messages, tokenUsage, addMessage, clearMessages, buildHistory, genId, MAX_MESSAGES,
} from '../store'

/** 模拟本地存储。Mock local storage. */
const localStore = (globalThis as any).__localStore as Map<string, string>

/** store 消息管理测试套件。Store message management test suite. */
describe('store 消息管理', () => {
  /** 每个测试前清空消息和本地存储。Clear messages and local storage before each test. */
  beforeEach(() => {
    clearMessages()
    localStore.clear()
  })

  /** 测试 addMessage 追加消息并限制上限。Test addMessage appends messages and enforces limit. */
  it('addMessage 追加消息并限制上限', () => {
    for (let i = 0; i < MAX_MESSAGES + 10; i++) addMessage('user', `msg${i}`)
    expect(messages.value.length).toBe(MAX_MESSAGES)
    expect(messages.value[0].text).toBe('msg10')
  })

  /** 测试 buildHistory 不含 system，工具结果拼入 assistant 内容。
   *  Test buildHistory excludes system messages, tool results appended to assistant content. */
  it('buildHistory 不含 system，工具结果拼入 assistant 内容', () => {
    addMessage('user', '查天气')
    messages.value.push({
      id: genId(), role: 'assistant', text: '结果',
      toolCalls: [{ id: 't1', name: 'get_weather', args: {}, status: 'done', result: '晴' }],
      timestamp: Date.now(),
    })
    const h = buildHistory()
    expect(h.some(m => m.role === 'system')).toBe(false)
    const last = h[h.length - 1]
    expect(last.content).toContain('[工具 get_weather 执行结果]')
    expect(last.content).toContain('晴')
  })

  /** 测试消息与 token 用量经 debounce 持久化到 localStorage。
   *  Test messages and token usage persist to localStorage with debounce. */
  it('消息与 token 用量经 debounce 持久化到 localStorage', async () => {
    addMessage('user', 'hi')
    tokenUsage.value = { total_tokens: 10 }
    await new Promise(r => setTimeout(r, 700))  // 等待 500ms debounce 落盘。Wait for 500ms debounce to persist.
    const saved = JSON.parse(localStore.get('xluo.history') || '{}')
    expect(saved.messages.length).toBe(1)
    expect(saved.messages[0].text).toBe('hi')
    expect(saved.tokenUsage.total_tokens).toBe(10)
  })
})
