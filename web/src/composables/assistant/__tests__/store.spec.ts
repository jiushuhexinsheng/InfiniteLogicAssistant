import { describe, it, expect, beforeEach } from 'vitest'
import {
  messages, tokenUsage, addMessage, clearMessages, buildHistory, genId, MAX_MESSAGES,
} from '../store'

const localStore = (globalThis as any).__localStore as Map<string, string>

describe('store 消息管理', () => {
  beforeEach(() => {
    clearMessages()
    localStore.clear()
  })

  it('addMessage 追加消息并限制上限', () => {
    for (let i = 0; i < MAX_MESSAGES + 10; i++) addMessage('user', `msg${i}`)
    expect(messages.value.length).toBe(MAX_MESSAGES)
    expect(messages.value[0].text).toBe('msg10')
  })

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

  it('消息与 token 用量经 debounce 持久化到 localStorage', async () => {
    addMessage('user', 'hi')
    tokenUsage.value = { total_tokens: 10 }
    await new Promise(r => setTimeout(r, 700))  // 等待 500ms debounce 落盘
    const saved = JSON.parse(localStore.get('xluo.history') || '{}')
    expect(saved.messages.length).toBe(1)
    expect(saved.messages[0].text).toBe('hi')
    expect(saved.tokenUsage.total_tokens).toBe(10)
  })
})
