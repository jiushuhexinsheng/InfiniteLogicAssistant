import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api', () => ({ api: { createSession: vi.fn() }, streamUtter: vi.fn() }))
vi.mock('../assistant/store', () => ({
  createNewSession: vi.fn(),
  switchSession: vi.fn(),
  state: { value: 'done' },
  currentSessionId: { value: 's1' },
}))

import { api } from '../../api'
import { notify } from '../useToast'
import { createNewSession } from '../assistant/store'
import { useConsole, newSession, CONSOLE_TABS } from '../useConsole'

/**
 * 新建会话（2026-10-11 随按钮迁入 useConsole：侧栏「新建」触发）。
 * Create a new session (moved into useConsole on 2026-10-11 with the sidebar button).
 */
/**
 * 任务库下线（docs/designs/10 6.1）：TaskStore 无任何运行时写入方，任务库 tab 永远
 * 是空列表，产品上不再暴露。后端 /api/library 保留一个版本返回空/410。
 * Task library offline (docs/designs/10 6.1): TaskStore has no runtime writer, so the
 * tab could only ever show an empty list; it is no longer exposed.
 */
describe('控制台导航不再包含任务库', () => {
  it('CONSOLE_TABS 没有 library 项', () => {
    expect(CONSOLE_TABS.some(t => t.key === 'library')).toBe(false)
    expect(CONSOLE_TABS.some(t => t.label === '任务库')).toBe(false)
  })
})

describe('useConsole.newSession', () => {
  beforeEach(() => {
    vi.mocked(api.createSession).mockReset()
    vi.mocked(createNewSession).mockReset()
    vi.restoreAllMocks()
  })

  it('成功 → 切换会话、回到对话页并提示', async () => {
    vi.mocked(api.createSession).mockResolvedValue({ ok: true, session: { id: 's9' } } as any)
    const okSpy = vi.spyOn(notify, 'ok')
    useConsole().activeTab.value = 'settings'
    await newSession()
    expect(createNewSession).toHaveBeenCalledWith('s9')
    expect(okSpy).toHaveBeenCalledWith('已新建会话')
    expect(useConsole().activeTab.value).toBe('conv')
  })

  it('失败 → 错误通知而非静默', async () => {
    vi.mocked(api.createSession).mockRejectedValue(new Error('会话数超限'))
    const errSpy = vi.spyOn(notify, 'err')
    await newSession()
    expect(errSpy).toHaveBeenCalledWith('新建会话失败：会话数超限')
    expect(createNewSession).not.toHaveBeenCalled()
  })
})
