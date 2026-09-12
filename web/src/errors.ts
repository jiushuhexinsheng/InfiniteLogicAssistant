/**
 * 错误文案统一入口：全站唯一的错误 → 字符串转换点。
 * Central error-message entry: the single error-to-string conversion point.
 */

/**
 * 把任意异常转成可展示的错误文案。
 * Convert any thrown value into a displayable error message.
 *
 * @param e 捕获到的异常。The caught exception.
 * @returns 错误文案；空值回退为「未知错误」。The message, falling back to a generic one for empty values.
 */
export function formatError(e: unknown): string {
  if (e instanceof Error) return e.message || '未知错误'
  if (typeof e === 'string') return e.trim() || '未知错误'
  if (e === null || e === undefined) return '未知错误'
  return String(e)
}
