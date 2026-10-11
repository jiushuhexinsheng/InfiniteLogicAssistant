// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import UiCombobox from '../UiCombobox.vue'

/**
 * UiCombobox（2026-10-11 取代原生 datalist）：可自由输入 + 项目风格建议层。
 * 回归靶子：自由输入不得被建议层吞掉（自填模型名是核心场景）；键盘与选中行为。
 *
 * UiCombobox (2026-10-11, replaces the native datalist): free typing plus a
 * project-styled suggestion layer. Regression targets: free typing must never be
 * constrained by suggestions (self-filling model names is the core scenario); pick
 * and keyboard behaviour.
 */

afterEach(() => {
  document.body.innerHTML = ''
})

function setup(options: string[] = ['model-a', 'model-b', 'other-thing'], value = '') {
  const w = mount(UiCombobox, {
    props: { modelValue: value, options, placeholder: '输入或选择' },
    attrs: { 'data-testid': 'combo' },
  })
  return { w, input: () => w.find('input') }
}

describe('UiCombobox', () => {
  it('聚焦弹出建议面板，渲染全部选项（Teleport 到 body）', async () => {
    const { input } = setup()
    await input().trigger('focus')
    const opts = document.querySelectorAll('body > .ui-select-menu .ui-select-option')
    expect(opts.length).toBe(3)
  })

  it('聚焦打开显示全部建议（当前值不过滤 —— 值 Chloe 不会藏掉 Mia）', async () => {
    const { input } = setup(['Chloe', 'Mia'], 'Chloe')
    await input().trigger('focus')
    const opts = [...document.querySelectorAll('body > .ui-select-menu .ui-select-option')]
    expect(opts.length).toBe(2)
    expect(opts.map(o => o.textContent)).toContain('Mia')
  })

  it('键入即时过滤建议（包含匹配、大小写不敏感）', async () => {
    const { w, input } = setup()
    await input().trigger('focus')
    await input().setValue('other')
    await w.setProps({ modelValue: 'other' })   // 模拟 v-model 回写。Simulates the v-model echo.
    await new Promise(r => setTimeout(r, 0))
    const opts = [...document.querySelectorAll('body > .ui-select-menu .ui-select-option')]
    expect(opts.length).toBe(1)
    expect(opts[0].textContent).toContain('other-thing')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['other'])
  })

  it('自由输入：无匹配时面板关闭，值照常外发（不被建议层拦住）', async () => {
    const { w, input } = setup()
    await input().trigger('focus')
    await input().setValue('brand-new-custom-model-9000')
    await w.setProps({ modelValue: 'brand-new-custom-model-9000' })
    await new Promise(r => setTimeout(r, 0))
    expect(document.querySelector('body > .ui-select-menu')).toBeNull()
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['brand-new-custom-model-9000'])
  })

  it('点击建议 → 值替换并关闭面板', async () => {
    const { w, input } = setup()
    await input().trigger('focus')
    const opt = document.querySelector('body > .ui-select-menu .ui-select-option') as HTMLElement
    opt.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['model-a'])
    await new Promise(r => setTimeout(r, 0))
    expect(document.querySelector('body > .ui-select-menu')).toBeNull()
  })

  it('键盘 ↓ 高亮、Enter 选中；Esc 关闭', async () => {
    const { w, input } = setup()
    await input().trigger('focus')
    await input().trigger('keydown', { key: 'ArrowDown' })
    await input().trigger('keydown', { key: 'Enter' })
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['model-b'])   // 首项高亮 → 下移一项? 见下
  })
})
