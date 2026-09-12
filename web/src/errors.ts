/**
 * 错误文案统一入口：全站唯一的错误 → 字符串转换点。
 * Central error-message entry: the single error-to-string conversion point.
 */

/**
 * 把任意异常转成可展示的错误文案。
 * Convert any thrown value into a displayable error message.
 *
 * @param e 捕获到的异常。The caught exception.
 * @param fallback 异常无可用信息时的兜底文案（缺省「未知错误」）。Fallback text when the exception carries no usable information (defaults to a generic message).
 * @returns 错误文案。The error message.
 */
export function formatError(e: unknown, fallback = '未知错误'): string {
  if (e instanceof Error) return e.message || fallback
  if (typeof e === 'string') return e.trim() || fallback
  if (e === null || e === undefined) return fallback
  return String(e)
}
