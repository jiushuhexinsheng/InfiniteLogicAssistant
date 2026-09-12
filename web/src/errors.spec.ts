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

/** 领域化兜底：调用方可给出比「未知错误」更贴切的兜底文案。
 *  Domain-specific fallback: callers may supply a more apt fallback than the generic one. */
describe('formatError 兜底文案', () => {
  it('缺省兜底为「未知错误」', () => {
    expect(formatError(undefined)).toBe('未知错误')
  })

  it('无信息的异常改用调用方给的兜底文案', () => {
    expect(formatError(undefined, '执行失败')).toBe('执行失败')
    expect(formatError(new Error(''), '执行失败')).toBe('执行失败')
    expect(formatError('   ', '执行失败')).toBe('执行失败')
  })

  it('有信息时兜底文案不生效', () => {
    expect(formatError(new Error('端口被占用'), '执行失败')).toBe('端口被占用')
    expect(formatError('端口被占用', '执行失败')).toBe('端口被占用')
  })
})
