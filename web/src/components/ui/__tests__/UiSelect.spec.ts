// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'
import UiSelect from '../UiSelect.vue'

/** 最近挂载的 wrapper：统一由 Vue 卸载（Teleport 挂在 body，禁止粗暴 innerHTML 清场）。
 *  Latest mounted wrapper: unmounted by Vue (Teleport targets body; never wipe with innerHTML). */
let lastWrapper: VueWrapper<any> | null = null

afterEach(async () => {
  lastWrapper?.unmount()
  lastWrapper = null
  await flushPromises()
})

/**
 * 自绘下拉框：外壳触发器 + Teleport 弹层（原生 select 的系统弹层无法定制）。
 *
 * 回归靶子：选项从 slot 的 option vnode 解析（调用方 API 不变）；
 * 面板挂 body、选中写回 v-model、键盘 ↑↓/Enter/Esc、关闭复位。
 *
 * Custom select: trigger shell + teleported panel (the native popup cannot be styled).
 */
describe('UiSelect（自绘下拉框）', () => {
  /** 挂一个受控的 UiSelect。Mount a controlled UiSelect. */
  function mountSelect(initial = '') {
    const model = ref(initial)
    const w = mount({
      components: { UiSelect },
      template: `
        <UiSelect v-model="model">
          <option value="a">选项A</option>
          <option value="b">选项B</option>
          <option value="c">选项C</option>
        </UiSelect>
      `,
      setup: () => ({ model }),
    })
    lastWrapper = w
    return { w, model }
  }

  /** 默认折叠，触发器显示选中项 label。Collapsed by default; trigger shows the selected label. */
  it('默认折叠，触发器回显选中项', () => {
    const { w } = mountSelect('b')
    expect(w.find('.ui-select').exists()).toBe(true)
    expect(w.find('.ui-select-value').text()).toBe('选项B')
    expect(w.find('.ui-select-menu').exists()).toBe(false)
    // 选项未打开时不渲染 DOM（从 slot vnode 惰性解析）。Options are not in the DOM until open.
    expect(document.querySelector('.ui-select-menu')).toBeNull()
  })

  /** 点开面板：Teleport 到 body、选中项打勾。Open: teleported to body, selected checked. */
  it('点击展开面板并标记选中项', async () => {
    const { w } = mountSelect('b')
    await w.find('.ui-select').trigger('click')
    const menu = document.querySelector('.ui-select-menu')
    expect(menu, '面板应挂到 body').toBeTruthy()
    expect(menu!.getAttribute('role')).toBe('listbox')
    const opts = document.querySelectorAll('.ui-select-option')
    expect(opts.length).toBe(3)
    expect(opts[1].getAttribute('aria-selected')).toBe('true')
    expect(opts[1].classList.contains('sel')).toBe(true)
    expect(w.find('.ui-select').attributes('aria-expanded')).toBe('true')
  })

  /** 点选项：写回 v-model 并关闭。Pick: writes back v-model and closes. */
  it('点击选项写回值并关闭面板', async () => {
    const { w, model } = mountSelect('a')
    await w.find('.ui-select').trigger('click')
    const opt = document.querySelector('.ui-select-option[data-value="c"]') as HTMLElement
    opt.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(model.value).toBe('c')
    // DOM 卸载是异步的，等一个 tick。DOM unmount is async; wait a tick.
    await flushPromises()
    expect(document.querySelector('.ui-select-menu')).toBeNull()
    expect(w.find('.ui-select-value').text()).toBe('选项C')
  })

  /** 键盘：↑↓ 移动活动项，Enter 选择，Esc 关闭。Keyboard: ↑↓ moves, Enter picks, Esc closes. */
  it('键盘导航：ArrowDown + Enter 选中，Esc 关闭', async () => {
    const { w, model } = mountSelect('a')
    const trigger = w.find('.ui-select')
    // 首次 ArrowDown 仅打开并定位到选中项（索引 0）。First ArrowDown only opens, anchored at the selected item (index 0).
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    expect(document.querySelector('.ui-select-menu')).toBeTruthy()
    expect(trigger.attributes('aria-activedescendant')).toContain('-0')
    // 再按一次移到下一项 b（索引 1）。Second press moves to b (index 1).
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    expect(trigger.attributes('aria-activedescendant')).toContain('-1')
    await trigger.trigger('keydown', { key: 'Enter' })
    expect(model.value).toBe('b')
    await flushPromises()
    expect(document.querySelector('.ui-select-menu')).toBeNull()

    // Esc 关闭。Esc closes.
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    expect(document.querySelector('.ui-select-menu')).toBeTruthy()
    await trigger.trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(document.querySelector('.ui-select-menu')).toBeNull()
  })

  /** 禁用态不响应点击。Disabled ignores clicks. */
  it('禁用时不展开面板', async () => {
    const w = mount(UiSelect, {
      props: { disabled: true, modelValue: '' },
      slots: { default: '<option value="a">A</option>' },
    })
    lastWrapper = w
    await w.find('.ui-select').trigger('click')
    expect(document.querySelector('.ui-select-menu')).toBeNull()
  })

  /** 值不在选项内时回退原值显示。Unmatched value falls back to the raw value. */
  it('未命中选项时触发器回显原值', () => {
    const { w } = mountSelect('zzz')
    expect(w.find('.ui-select-value').text()).toBe('zzz')
    expect(w.find('.ui-select-value').classes()).not.toContain('ph')
  })

  /** 空值且无匹配：显示占位文案。Empty value with no match: shows placeholder. */
  it('空值显示占位文案', () => {
    const w = mount(UiSelect, {
      props: { modelValue: '', placeholder: '请选择一个' },
      slots: { default: '<option value="a">A</option>' },
    })
    lastWrapper = w
    expect(w.find('.ui-select-value').text()).toBe('请选择一个')
    expect(w.find('.ui-select-value').classes()).toContain('ph')
  })

  /** 回归靶子：面板内滚动与打开宽限期内的焦点滚动不关闭；宽限期外的外部滚动才关闭。
   *
   * 两类非用户意图的滚动曾导致「点开即关」：
   * 1. 面板自身 scrollIntoView（选项多的真实环境必滚）；
   * 2. 浏览器打开瞬间为聚焦按钮微滚祖先容器（.console-settings 等，异步分帧、只在满视口页面复现）。
   *
   * Regression: in-panel scrolls and the post-open focus-scroll grace period must not
   * close the panel; only outside scrolls after the grace period do. */
  it('面板内滚动不关闭，宽限期外的外部滚动才关闭', async () => {
    const { w } = mountSelect('a')
    await w.find('.ui-select').trigger('click')
    const menu = document.querySelector('.ui-select-menu')
    expect(menu).toBeTruthy()

    // 面板内部滚动（scroll 不冒泡，window 捕获阶段仍能收到）。In-panel scroll (non-bubbling; window capture still sees it).
    menu!.dispatchEvent(new Event('scroll'))
    await flushPromises()
    expect(document.querySelector('.ui-select-menu'), '面板内滚动不应关闭面板').toBeTruthy()

    // 打开宽限期（300ms）内的外部滚动：焦点/连锁滚动，放行。
    // Outside scroll within the open grace period (300ms): focus/chain scroll, pass.
    window.dispatchEvent(new Event('scroll'))
    await flushPromises()
    expect(document.querySelector('.ui-select-menu'), '宽限期内的外部滚动不应关闭面板').toBeTruthy()

    // 过了宽限期，外部滚动关闭（防面板错位）。After the grace period, outside scroll closes (prevents misalignment).
    await new Promise(r => setTimeout(r, 350))
    window.dispatchEvent(new Event('scroll'))
    await flushPromises()
    expect(document.querySelector('.ui-select-menu'), '宽限期外的外部滚动应关闭面板').toBeNull()
  })
})
