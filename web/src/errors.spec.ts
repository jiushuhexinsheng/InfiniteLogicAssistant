import { describe, expect, it } from 'vitest'
import { formatError } from './errors'

/** formatError 的单元测试。Unit tests for formatError. */
describe('formatError', () => {
  it('提取 Error 的 message', () => {
    expect(formatError(new Error('连接超时'))).toBe('连接超时')
  })

  it('字符串原样返回', () => {
    expect(formatError('后端拒绝')).toBe('后端拒绝')
  })

  it('空值回退为未知错误', () => {
    expect(formatError(undefined)).toBe('未知错误')
    expect(formatError(null)).toBe('未知错误')
    expect(formatError('')).toBe('未知错误')
  })

  it('任意对象转为字符串', () => {
    expect(formatError({ code: 500 })).toBe('[object Object]')
  })
})
