// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConsoleSidebar from '../ConsoleSidebar.vue'
import { useConsole } from '../../../composables/useConsole'

/**
 * 侧栏改版（2026-10-11 用户要求）：新建/清空并排置顶、可折叠（图标态持久化）、
 * 历史入口保留在导航中。
 * Sidebar rework (2026-10-11 user request): New/Clear side by side at the top,
 * collapsible (icon-only state persisted), History stays in the nav.
 */
describe('ConsoleSidebar', () => {
  beforeEach(() => {
    useConsole().sidebarCollapsed.value = false
  })

  it('不放新建/清空（2026-10-11 用户裁定：动作在对话页左上，不进菜单）', () => {
    const w = mount(ConsoleSidebar, { props: { active: 'conv', wakeEnabled: true } })
    expect(w.text()).not.toContain('新建')
    expect(w.text()).not.toContain('清空')
  })

  it('折叠开关切换 collapsed 类并写入单例', async () => {
    const w = mount(ConsoleSidebar, { props: { active: 'conv', wakeEnabled: false } })
    const fold = w.find('.sb-fold')
    await fold.trigger('click')
    expect(w.find('.console-sidebar').classes()).toContain('collapsed')
    expect(useConsole().sidebarCollapsed.value).toBe(true)
    await fold.trigger('click')
    expect(w.find('.console-sidebar').classes()).not.toContain('collapsed')
    expect(useConsole().sidebarCollapsed.value).toBe(false)
  })

  it('导航保留历史入口（折叠不影响可达性，这里先断言存在）', () => {
    const w = mount(ConsoleSidebar, { props: { active: 'conv', wakeEnabled: false } })
    expect(w.text()).toContain('历史')
  })
})
