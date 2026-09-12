import { ref, type Ref } from 'vue'
import { formatError } from '../errors'

/**
 * useAsync 的返回结构。The shape returned by useAsync.
 */
export interface UseAsyncResult<T> {
  /** 最近一次成功的结果。The most recent successful result. */
  data: Ref<T | null>
  /** 最近一次失败的错误文案（成功时清空）。The last failure message (cleared on success). */
  error: Ref<string | null>
  /** 是否正在执行。Whether a call is in flight. */
  loading: Ref<boolean>
  /** 触发调用；失败不抛出，错误写入 error。Trigger the call; failures are captured, not thrown. */
  run: (...args: any[]) => Promise<T | null>
}

/**
 * 把一次异步调用包成 { data, error, loading, run }，统一错误捕获与文案格式化。
 * Wrap an async call into { data, error, loading, run } with unified error capture
 * and message formatting.
 *
 * @param fn 被包装的异步函数。The async function to wrap.
 * @returns 响应式状态与触发函数。Reactive state and the trigger function.
 */
export function useAsync<T>(fn: (...args: any[]) => Promise<T>): UseAsyncResult<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref<string | null>(null)
  const loading = ref(false)

  async function run(...args: any[]): Promise<T | null> {
    loading.value = true
    error.value = null
    try {
      const r = await fn(...args)
      data.value = r
      return r
    } catch (e) {
      error.value = formatError(e)
      return null
    } finally {
      loading.value = false
    }
  }

  return { data, error, loading, run }
}
