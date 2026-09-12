import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { notify, useToast } from './useToast'

/** useToast 的单元测试。Unit tests for useToast. */
describe('useToast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    notify.clear()
  })
  afterEach(() => {
    notify.clear()
    vi.useRealTimers()
  })

  it('入队后出现在 items 中并带类型', () => {
    const { items } = useToast()
    notify.ok('已保存')
    expect(items.value).toHaveLength(1)
    expect(items.value[0].kind).toBe('ok')
    expect(items.value[0].text).toBe('已保存')
  })

  it('到达存活时长后自动消失', () => {
    const { items } = useToast()
    notify.info('提示')
    expect(items.value).toHaveLength(1)
    vi.advanceTimersByTime(4000)
    expect(items.value).toHaveLength(0)
  })

  it('错误类型存活更久（6000ms）', () => {
    const { items } = useToast()
    notify.err('保存失败')
    vi.advanceTimersByTime(4000)
    expect(items.value).toHaveLength(1)
    vi.advanceTimersByTime(2000)
    expect(items.value).toHaveLength(0)
  })

  it('dismiss 立即移除指定条目', () => {
    const { items } = useToast()
    notify.info('提示')
    const id = items.value[0].id
    notify.dismiss(id)
    expect(items.value).toHaveLength(0)
  })

  it('多条并存，各自独立计时', () => {
    const { items } = useToast()
    notify.ok('a')
    notify.ok('b')
    expect(items.value).toHaveLength(2)
  })
})
