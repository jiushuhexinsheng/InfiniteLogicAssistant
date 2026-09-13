// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../../api', () => ({
  api: {
    patchConfig: vi.fn(), getConfigFull: vi.fn(), getProviders: vi.fn(),
    getTools: vi.fn(), getDetection: vi.fn(),
  },
}))

import { api } from '../../../../api'
import { editable } from '../state'
import PermissionsCard from '../PermissionsCard.vue'

/**
 * 权限设置卡：三个层级下拉 + 默认动作 + 规则增删。
 * Permission settings card: three tier dropdowns, a default action, and rule add/remove.
 */
const PERMS = {
  default_action: 'ask',
  tiers: { read: 'allow', write: 'ask', exec: 'ask' },
  rules: [{ match: 'run_shell_tool', action: 'deny' }],
}

describe('PermissionsCard', () => {
  beforeEach(() => {
    vi.mocked(api.getTools).mockReset()
    vi.mocked(api.getTools).mockResolvedValue({ ok: true, tools: [] } as any)
    editable.value = { permissions: structuredClone(PERMS) } as any
  })

  /** 渲染层级下拉并反映当前配置。Renders the tier dropdowns reflecting the current config. */
  it('渲染层级下拉并反映当前配置', () => {
    const w = mount(PermissionsCard)
    // read / write / exec 三个层级 + default_action，共 4 个下拉
    expect(w.findAll('select').length).toBeGreaterThanOrEqual(4)
    expect(w.html()).toContain('run_shell_tool')
    expect(w.text()).toContain('工具权限')
  })

  /** 改变 read 层级会写回 editable。Changing the read tier writes back to editable. */
  it('改变层级写回 editable', async () => {
    const w = mount(PermissionsCard)
    // 按初值定位 read 层级：模板里 default_action 下拉排在层级之前，不能靠下标取；
    // read 是唯一初值为 allow 的下拉。
    // Locate the read tier by its initial value: the default_action select precedes the
    // tier selects, so an index lookup would hit the wrong one; read is the only select
    // whose initial value is "allow".
    const readSelect = w.findAll('select')
      .find((s) => (s.element as HTMLSelectElement).value === 'allow')!
    await readSelect.setValue('deny')
    expect((editable.value as any).permissions.tiers.read).toBe('deny')
  })

  /** 新增规则追加一条空规则。Adding a rule appends an empty one. */
  it('新增规则追加一条空规则', async () => {
    const w = mount(PermissionsCard)
    await w.findAll('button').find((b) => b.text().includes('新增'))!.trigger('click')
    expect((editable.value as any).permissions.rules).toHaveLength(2)
  })

  /** 删除规则移除对应项。Deleting a rule removes it. */
  it('删除规则移除对应项', async () => {
    const w = mount(PermissionsCard)
    await w.findAll('button').find((b) => b.text() === '删除')!.trigger('click')
    expect((editable.value as any).permissions.rules).toHaveLength(0)
  })

  /** 工具名 datalist 来自 /api/tools。The tool-name datalist comes from /api/tools. */
  it('工具名 datalist 来自已注册工具', async () => {
    vi.mocked(api.getTools).mockResolvedValue({
      ok: true, tools: [{ function: { name: 'read_file' } }],
    } as any)
    const w = mount(PermissionsCard)
    await flushPromises()
    expect(w.find('datalist').html()).toContain('read_file')
  })
})
