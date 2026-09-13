import { describe, expect, it } from 'vitest'
import { matchOption } from '../answerMatch'

const OPTS = [
  { value: 'yes', label: '允许本次' },
  { value: 'no', label: '拒绝' },
]

/** 转写文本 → 选项匹配：**只做 trim 后精确相等**。
 *  Transcript → option matching: trim-then-exact-equality only. */
describe('matchOption', () => {
  /** 精确命中返回对应选项。An exact hit returns the matching option. */
  it('精确命中返回选项', () => {
    expect(matchOption('允许本次', OPTS)?.value).toBe('yes')
    expect(matchOption('拒绝', OPTS)?.value).toBe('no')
  })

  /** 两侧空白被 trim 后仍命中。Surrounding whitespace is trimmed before comparing. */
  it('两侧空白 trim 后命中', () => {
    expect(matchOption('  允许本次  ', OPTS)?.value).toBe('yes')
  })

  /** 不命中返回 null。A miss returns null. */
  it('不命中返回 null', () => {
    expect(matchOption('好的', OPTS)).toBeNull()
    expect(matchOption('', OPTS)).toBeNull()
  })

  /** 子串不算命中 —— 这是安全边界，绝不能放宽为包含匹配。
   *  A substring is not a hit — this is the safety boundary and must never be relaxed
   *  to containment matching. */
  it('子串不命中（安全边界）', () => {
    expect(matchOption('我不允许本次', OPTS)).toBeNull()
    expect(matchOption('允许', OPTS)).toBeNull()
    expect(matchOption('拒绝吧', OPTS)).toBeNull()
  })

  /** 归一化一律不做：大小写/全角半角/标点差异都视为不命中。
   *  No normalisation at all: case, full/half-width and punctuation differences all miss. */
  it('不做任何归一化', () => {
    expect(matchOption('允许本次。', OPTS)).toBeNull()
    expect(matchOption('允许 本次', OPTS)).toBeNull()
  })

  /** 空选项列表返回 null。An empty option list returns null. */
  it('空选项列表返回 null', () => {
    expect(matchOption('允许本次', [])).toBeNull()
  })
})
