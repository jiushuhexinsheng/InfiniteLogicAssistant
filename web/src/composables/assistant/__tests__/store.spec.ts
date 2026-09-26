import { describe, it, expect, beforeEach } from 'vitest'
import {
  messages, tokenUsage, addMessage, clearMessages, buildHistory, genId, MAX_MESSAGES,
  switchSession, currentSessionId,
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

  /** 测试 buildHistory 不含 system，tool 块结果拼入 assistant 内容。
   *  Test buildHistory excludes system messages, tool block results appended to assistant content. */
  it('buildHistory 不含 system，工具结果拼入 assistant 内容', () => {
    addMessage('user', '查天气')
    messages.value.push({
      id: genId(), role: 'assistant', text: '结果',
      blocks: [
        { v: 1, id: 'b1', type: 'text', ts: new Date().toISOString(), payload: { md: '结果' } },
        { v: 1, id: 'b2', type: 'tool', ts: new Date().toISOString(),
          payload: { name: 'get_weather', output: '晴', status: 'ok' } },
      ],
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

/** 历史贯通：switchSession 块还原 + 真实时间戳（阶段 5 验收）。
 *  History integration: switchSession restores blocks + real timestamps. */
describe('store switchSession 历史贯通', () => {
  beforeEach(() => {
    messages.value = []
    currentSessionId.value = ''
  })

  /** 新历史（含 blocks/ts）完整还原：块结构 + 消息真实时间戳。
   *  New-format history restores blocks + the message's real timestamp. */
  it('含 blocks/ts 的历史完整还原', () => {
    const toolBlk = { v: 1, id: 'b2', type: 'tool', ts: 't2', turn_id: 'turn_1',
                      agent: '', meta: {}, payload: { name: 'run_shell_tool', output: 'ok' } }
    switchSession('conv-1', [
      { role: 'user', content: '跑个命令', blocks: [{ v: 1, id: 'b1', type: 'text', ts: 't1', payload: { md: '跑个命令' } }], ts: '2026-09-26T10:00:00' },
      { role: 'assistant', content: 'run_shell_tool: ok', blocks: [toolBlk], ts: '2026-09-26T10:01:00' },
    ])
    expect(currentSessionId.value).toBe('conv-1')
    expect(messages.value).toHaveLength(2)
    expect(messages.value[1].blocks[0].type).toBe('tool')
    // 真实时间戳（不再是 Date.now() 伪造）
    expect(new Date(messages.value[1].timestamp).toISOString()).toBe(new Date('2026-09-26T10:01:00').toISOString())
  })

  /** 无 blocks 的裸消息包装为 text 块（不丢内容）。
   *  Bare messages without blocks are wrapped into a text block (nothing lost). */
  it('无 blocks 的消息包装为 text 块', () => {
    switchSession('conv-2', [{ role: 'user', content: '旧消息' }])
    expect(messages.value[0].blocks[0].type).toBe('text')
    expect(messages.value[0].blocks[0].payload.md).toBe('旧消息')
    expect(messages.value[0].text).toBe('旧消息')
  })
})
