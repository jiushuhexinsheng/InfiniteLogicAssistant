import { describe, expect, it } from 'vitest'
import { useAsync } from './useAsync'

/** useAsync 的单元测试。Unit tests for useAsync. */
describe('useAsync', () => {
  it('成功时写入 data 并复位 loading', async () => {
    const { data, error, loading, run } = useAsync(async () => 42)
    const p = run()
    expect(loading.value).toBe(true)
    expect(await p).toBe(42)
    expect(data.value).toBe(42)
    expect(error.value).toBeNull()
    expect(loading.value).toBe(false)
  })

  it('失败时写入 error 且 data 保持为 null', async () => {
    const { data, error, loading, run } = useAsync(async () => {
      throw new Error('拉取失败')
    })
    expect(await run()).toBeNull()
    expect(error.value).toBe('拉取失败')
    expect(data.value).toBeNull()
    expect(loading.value).toBe(false)
  })

  it('再次 run 会先清空上一次的 error', async () => {
    let shouldFail = true
    const { data, error, run } = useAsync(async () => {
      if (shouldFail) throw new Error('第一次失败')
      return 'ok'
    })
    await run()
    expect(error.value).toBe('第一次失败')
    shouldFail = false
    await run()
    expect(error.value).toBeNull()
    expect(data.value).toBe('ok')
  })

  it('透传参数给被包装函数', async () => {
    const { data, run } = useAsync(async (a: number, b: number) => a + b)
    await run(2, 3)
    expect(data.value).toBe(5)
  })
})
