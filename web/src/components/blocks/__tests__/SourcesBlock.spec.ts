// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SourcesBlock from '../SourcesBlock.vue'
import { makeBlock } from '../../../blocks/normalize'
import { summarizeBlock, speakBlock, hasBlock } from '../../../blocks/registry'
import '../../../blocks/index'  // 注册副作用（sources 一并注册）。Registration side effects.

/**
 * RAG 来源块（docs/designs/05 §3.2）：默认折叠、展开列 chips、注册协议完整。
 * RAG sources block (docs/designs/05 §3.2): collapsed by default, chips on expand,
 * complete registry contract.
 */
describe('SourcesBlock', () => {
  const items = [
    { n: 1, path: 'docs/env.md', section: '系统', score: 2.5123 },
    { n: 2, path: 'docs/rag.md', section: '', score: 1.2 },
  ]

  /** 默认折叠（meta.collapsed=true）：只显示头部计数，不列条目。
   *  Collapsed by default (meta.collapsed=true): header count only, no entries. */
  it('默认折叠只显示来源计数', () => {
    const b = makeBlock('sources', { items }, { collapsed: true } as any)
    // makeBlock 后端口径：meta 由后端下发；这里手动置 collapsed 模拟。
    b.meta = { ...b.meta, collapsed: true }
    const w = mount(SourcesBlock, { props: { block: b } })
    expect(w.text()).toContain('来源 2 个')
    expect(w.find('.bs-list').exists()).toBe(false)
  })

  /** 展开后列出编号/标题/路径/分数；section 空时回退文件名。
   *  Expanding lists number/title/path/fallback; empty section falls back to the file name. */
  it('展开列出来源条目', async () => {
    const b = makeBlock('sources', { items })
    b.meta = { ...b.meta, collapsed: true }
    const w = mount(SourcesBlock, { props: { block: b } })
    await w.find('.bs-head').trigger('click')
    expect(w.find('.bs-list').exists()).toBe(true)
    const text = w.text()
    expect(text).toContain('[1]')
    expect(text).toContain('系统')
    expect(text).toContain('docs/env.md')
    expect(text).toContain('2.51')          // 分数两位小数。Score to two decimals.
    expect(text).toContain('rag.md')        // section 空 → 路径末段兜底可见。Empty section → path visible.
  })

  /** 注册协议：sources 已注册（组件 + 摘要 + 不播报）。
   *  Registry contract: sources registered (component + summarize + silent). */
  it('注册协议完整', () => {
    expect(hasBlock('sources')).toBe(true)
    const b = makeBlock('sources', { items })
    expect(summarizeBlock(b)).toBe('📄 2 个来源')
    expect(speakBlock(b)).toBeNull()
  })
})
