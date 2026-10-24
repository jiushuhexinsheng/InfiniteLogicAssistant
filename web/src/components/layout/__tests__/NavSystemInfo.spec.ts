// @vitest-environment jsdom
/** 顶栏模型段优先显示模型名。The header's model segment prefers the model name. */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({ config: { value: null as any } }))

vi.mock('../../../composables/useApi', () => ({
  useConfig: () => ({ config: mocks.config }),
}))
vi.mock('../../../composables/useAssistant', () => ({
  useAssistant: () => ({
    stateColor: { value: '#fff' },
    stateLabel: { value: '在线' },
    wakeHint: { value: '衍衡' },
  }),
}))

import NavSystemInfo from '../NavSystemInfo.vue'

describe('NavSystemInfo', () => {
  it('有 llm_model 时显示模型名', () => {
    mocks.config.value = { llm_model: 'gpt-4o-mini', llm_profile: 'openai' }
    const w = mount(NavSystemInfo)
    expect(w.find('.nsi-model').text()).toContain('gpt-4o-mini')
  })

  it('无模型名时回退供应商名', () => {
    mocks.config.value = { llm_model: '', llm_profile: 'openai' }
    const w = mount(NavSystemInfo)
    expect(w.find('.nsi-model').text()).toContain('openai')
  })

  it('都没配置时显示未配置', () => {
    mocks.config.value = { llm_model: '', llm_profile: '' }
    const w = mount(NavSystemInfo)
    expect(w.find('.nsi-model').text()).toContain('未配置')
  })
})
