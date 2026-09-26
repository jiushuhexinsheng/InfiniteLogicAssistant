import { readFileSync } from 'fs'
import { resolve } from 'path'
import { describe, expect, it } from 'vitest'
import { detectWake } from '../wakeMatch'

/**
 * 共享测试向量（tests/data/wake_vectors.json，与后端 pytest 同一份）——
 * 钉住前端 wakeMatch.ts 与后端 core/voice/wake.py 的判定语义一致。
 * 改任一侧的匹配规则，两侧测试必须同时变绿。
 *
 * Shared test vectors (tests/data/wake_vectors.json, the same file the backend
 * pytest consumes) — pinning identical semantics between frontend wakeMatch.ts
 * and backend wake.py. Change the matching rules on either side and both suites
 * must stay green together.
 */
const vectors = JSON.parse(
  readFileSync(resolve(__dirname, '../../../../../tests/data/wake_vectors.json'), 'utf-8'),
) as {
  keywords: string[]
  positives: { text: string; command: string }[]
  negatives: { text: string }[]
}

describe('wakeMatch 共享向量（前后端语义对齐）', () => {
  it('正例全部命中且指令切分一致', () => {
    for (const c of vectors.positives) {
      const r = detectWake(c.text, vectors.keywords)
      expect(r.matched, `positive: ${c.text}`).toBe(true)
      expect(r.command, `positive: ${c.text}`).toBe(c.command)
    }
  })

  it('反例一条都不能命中', () => {
    for (const c of vectors.negatives) {
      const r = detectWake(c.text, vectors.keywords)
      expect(r.matched, `negative: ${c.text}`).toBe(false)
    }
  })
})
