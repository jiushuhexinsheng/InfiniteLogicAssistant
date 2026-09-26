import { describe, expect, it } from 'vitest'
import { registerBlock, getBlockSpec, summarizeBlock, speakBlock, hasBlock, setFallbackBlock } from '../registry'
import '../index'  // 注册副作用：内置块类型 Registration side effects: built-in block types

/** 块注册协议：新块即插即用，未注册兜底不丢数据。
 *  Block registry protocol: new blocks plug in; unregistered falls back without data loss. */
describe('块注册协议', () => {
  /** 内置块类型均已注册。Built-in block types are registered. */
  it('内置块类型已注册', () => {
    for (const t of ['thinking', 'tool', 'text', 'code', 'image', 'file', 'question', 'answer', 'notice', 'summary']) {
      expect(hasBlock(t)).toBe(true)
    }
  })

  /** 注册扩展块（ext:）后不改页面即可取回规格。
   *  An extension block (ext:) is retrievable without touching any page. */
  it('扩展块注册后即插即用', () => {
    const Comp = { template: '<div>chart</div>' }
    registerBlock('ext:chart', {
      component: Comp,
      summarize: (b) => `chart(${b.payload.kind})`,
      speak: () => null,
    })
    expect(hasBlock('ext:chart')).toBe(true)
    expect(getBlockSpec('ext:chart').component).toBe(Comp)
    expect(summarizeBlock({ v: 1, id: 'x', type: 'ext:chart', ts: '', payload: { kind: 'bar' } })).toBe('chart(bar)')
  })

  /** 未注册类型走兜底（摘要退化为类型名、默认不播）。
   *  Unregistered types fall back (summary degrades to type name; silent). */
  it('未注册类型走 UnknownBlock 兜底', () => {
    const b = { v: 1, id: 'x', type: 'ext:unknown-thing', ts: '', payload: {} }
    expect(summarizeBlock(b)).toBe('[ext:unknown-thing]')
    expect(speakBlock(b)).toBeNull()
  })
})
