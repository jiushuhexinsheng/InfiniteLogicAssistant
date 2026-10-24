// @vitest-environment jsdom
/** 对话内模型切换器：按供应商分组、当前项、选择持久化、失败回滚。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import ModelPicker from '../ModelPicker.vue'

const mocks = vi.hoisted(() => ({
  getLlmModels: vi.fn(),
  setActiveModel: vi.fn(),
  refreshConfig: vi.fn(),
  notifyErr: vi.fn(),
  config: { value: { llm_model: 'm1' } as any },
}))

vi.mock('../../../api', () => ({
  api: { getLlmModels: mocks.getLlmModels, setActiveModel: mocks.setActiveModel },
}))
vi.mock('../../../composables/useApi', () => ({
  useConfig: () => ({ config: mocks.config, refreshConfig: mocks.refreshConfig }),
}))
vi.mock('../../../composables/useToast', () => ({
  notify: { err: mocks.notifyErr, ok: vi.fn() },
}))

const DATA = {
  ok: true,
  active: { provider: 'p1', model: 'm1' },
  groups: [
    { provider: 'p1', label: 'p1', models: ['m1', 'm2'], current_model: 'm1' },
    { provider: 'p2', label: 'p2', models: ['x'], current_model: 'x' },
  ],
  error: null,
}

let lastWrapper: VueWrapper<any> | null = null
afterEach(async () => {
  lastWrapper?.unmount()
  lastWrapper = null
  await flushPromises()
})

function mountPicker() {
  lastWrapper = mount(ModelPicker)
  return lastWrapper
}

describe('ModelPicker', () => {
  beforeEach(() => {
    mocks.getLlmModels.mockReset().mockResolvedValue(DATA)
    mocks.setActiveModel.mockReset().mockResolvedValue({ ok: true, active: { provider: 'p1', model: 'm2' } })
    mocks.refreshConfig.mockClear()
    mocks.notifyErr.mockClear()
  })

  it('触发器显示当前模型；展开后按供应商分组', async () => {
    const w = mountPicker()
    await flushPromises()
    expect(w.find('.ui-gselect-value').text()).toBe('m1')

    await w.find('.ui-gselect').trigger('click')
    await flushPromises()

    expect([...document.querySelectorAll('.ui-gselect-group-label')].map(e => e.textContent))
      .toEqual(['p1', 'p2'])
    expect([...document.querySelectorAll('.ui-gselect-option-label')].map(e => e.textContent))
      .toEqual(['m1', 'm2', 'x'])
  })

  it('选择模型：调用 setActiveModel、刷新清单与全局配置', async () => {
    const w = mountPicker()
    await flushPromises()
    await w.find('.ui-gselect').trigger('click')
    await flushPromises()

    ;(document.querySelectorAll('.ui-gselect-option')[1] as HTMLElement).click()
    await flushPromises()

    expect(mocks.setActiveModel).toHaveBeenCalledWith('p1', 'm2')
    expect(mocks.refreshConfig).toHaveBeenCalled()
    expect(mocks.getLlmModels).toHaveBeenCalledTimes(2)
  })

  it('切换失败：toast 且保留原选择', async () => {
    mocks.setActiveModel.mockRejectedValue(new Error('boom'))
    const w = mountPicker()
    await flushPromises()
    await w.find('.ui-gselect').trigger('click')
    await flushPromises()

    ;(document.querySelectorAll('.ui-gselect-option')[1] as HTMLElement).click()
    await flushPromises()
    await nextTick()

    expect(mocks.notifyErr).toHaveBeenCalled()
    expect(w.find('.ui-gselect-value').text()).toBe('m1')
  })

  it('没有任何模型时禁用并显示「未配置模型」', async () => {
    mocks.getLlmModels.mockResolvedValue({ ok: true, active: { provider: '', model: '' }, groups: [], error: null })
    const w = mountPicker()
    await flushPromises()

    expect(w.find('.ui-gselect').attributes('disabled')).toBeDefined()
    expect(w.find('.ui-gselect-value').text()).toBe('未配置模型')
  })
})
