// @vitest-environment jsdom
/** 统一双语按钮：中文主标签 + 英文副标签、事件、禁用/加载。 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsButton from '../SettingsButton.vue'

describe('SettingsButton', () => {
  it('同时渲染中英文标签', () => {
    const w = mount(SettingsButton, { props: { zh: '新增供应商', en: 'Add Provider' } })
    expect(w.text()).toContain('新增供应商')
    expect(w.text()).toContain('Add Provider')
    expect(w.find('.bi-label').classes()).toContain('stack')
  })

  it('点击触发父级监听（原生事件透传）', async () => {
    const hit = vi.fn()
    const w = mount({
      components: { SettingsButton },
      template: '<SettingsButton zh="设置" en="Set key" @click="hit" />',
      setup: () => ({ hit }),
    })
    await w.find('.settings-action-wrap').trigger('click')
    expect(hit).toHaveBeenCalledTimes(1)
  })

  it('disabled / loading 透传给底层按钮', () => {
    const w = mount(SettingsButton, { props: { zh: '保存', en: 'Save', disabled: true } })
    expect(w.find('button').attributes('disabled')).toBeDefined()
  })
})
