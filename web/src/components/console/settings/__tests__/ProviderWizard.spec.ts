// @vitest-environment jsdom
/** 向导第 1 步：ID/URL 校验、重名提示、编辑模式 ID 只读。Wizard step 1 validation and edit mode.
 *  面板由 UiModal Teleport 到 body，故用 document 查询而不是 wrapper.find。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ProviderWizard from '../ProviderWizard.vue'

const mocks = vi.hoisted(() => ({
  fetchModels: vi.fn(),
  putSecret: vi.fn().mockResolvedValue({ ok: true }),
  saveModule: vi.fn().mockResolvedValue(true),
  editable: { value: { llm: { active: '', profiles: {} as Record<string, any> } } },
  notifyErr: vi.fn(),
}))

vi.mock('../../../../api', () => ({
  api: { fetchModels: mocks.fetchModels, putSecret: mocks.putSecret },
}))
vi.mock('../useSettings', () => ({
  useSettings: () => ({ editable: mocks.editable, saveModule: mocks.saveModule }),
}))
vi.mock('../../../../composables/useToast', () => ({
  notify: { err: mocks.notifyErr, ok: vi.fn() },
}))

beforeEach(() => {
  mocks.fetchModels.mockReset()
  mocks.putSecret.mockClear()
  mocks.saveModule.mockClear()
  mocks.editable.value.llm = { active: '', profiles: {} }
  mocks.notifyErr.mockClear()
})

const PROFILES = { openai: { provider: 'openai', endpoint: 'https://api.openai.com', model: 'gpt-4o-mini' } }

let lastWrapper: VueWrapper<any> | null = null

afterEach(async () => {
  lastWrapper?.unmount()
  lastWrapper = null
  await flushPromises()
})

function mountWizard(editingId: string | null = null, profiles: Record<string, any> = PROFILES) {
  lastWrapper = mount(ProviderWizard, {
    props: { modelValue: true, section: 'llm', editingId, profiles },
  })
  return lastWrapper
}

function idInput(): HTMLInputElement {
  return document.querySelector('input[placeholder="例如 my-provider"]') as HTMLInputElement
}
function urlInput(): HTMLInputElement {
  return document.querySelector('input[placeholder="https://api.example.com"]') as HTMLInputElement
}
function nextButton(): HTMLButtonElement {
  // SettingsButton 的根是 span 包装，禁用态在内层 button 上。
  return document.querySelector('.pw-next button') as HTMLButtonElement
}
async function type(el: HTMLInputElement, value: string): Promise<void> {
  el.value = value
  el.dispatchEvent(new Event('input'))
  await nextTick()
}

describe('ProviderWizard 第 1 步', () => {
  it('非法 ID 显示原因且 Next 禁用', async () => {
    mountWizard()
    await type(idInput(), 'Bad ID')
    await type(urlInput(), 'https://api.example.com')

    expect(document.body.textContent).toContain('只能小写字母/数字/-/_')
    expect(nextButton().disabled).toBe(true)
  })

  it('重名显示「已被使用」而不是静默禁用', async () => {
    mountWizard()
    await type(idInput(), 'openai')
    await type(urlInput(), 'https://api.example.com')

    expect(document.body.textContent).toContain('该 ID 已被使用')
    expect(nextButton().disabled).toBe(true)
  })

  it('URL 缺协议时报错', async () => {
    mountWizard()
    await type(idInput(), 'my-provider')
    await type(urlInput(), 'api.example.com')

    expect(document.body.textContent).toContain('http:// 或 https://')
    expect(nextButton().disabled).toBe(true)
  })

  it('合法输入后 Next 可点，点击进入第 2 步', async () => {
    mountWizard()
    await type(idInput(), 'my-provider')
    await type(urlInput(), 'https://api.example.com')

    expect(nextButton().disabled).toBe(false)
    nextButton().click()
    await flushPromises()

    expect(document.body.textContent).toContain('连接与模型')
  })

  it('编辑模式 ID 只读', () => {
    mountWizard('openai')
    expect(idInput().disabled).toBe(true)
  })
})

/** 打开第 2 步：点第二个预设（DeepSeek，自带两个模型）。Open step 2 via a preset. */
async function openPreset(): Promise<void> {
  const preset = document.querySelectorAll<HTMLElement>('.pw-preset')[1]
  preset.click()
  await flushPromises()
}

describe('ProviderWizard 第 2 步', () => {
  it('拉取成功渲染复选列表，添加所选进入模型表格', async () => {
    mocks.fetchModels.mockResolvedValue({ ok: true, models: ['x', 'y'], count: 2 })
    mountWizard()
    await openPreset()

    document.querySelector<HTMLElement>('.pw-fetch')!.click()
    await flushPromises()
    expect(document.body.textContent).toContain('共 2 个')

    const first = document.querySelector<HTMLInputElement>('.fm-row input')!
    first.checked = true
    first.dispatchEvent(new Event('change'))
    await nextTick()
    document.querySelector<HTMLElement>('.fm-add')!.click()
    await flushPromises()

    const values = [...document.querySelectorAll<HTMLInputElement>('.mt-row input')]
      .map(i => i.value)
    expect(values).toContain('x')
    expect(document.body.textContent).not.toContain('选择要添加的模型')   // 添加后弹窗关闭
  })

  it('保存新供应商：有 key 才写 secrets，model 取列表首项并 emit saved', async () => {
    const w = mountWizard()
    await openPreset()
    const key = document.querySelector<HTMLInputElement>('.pw-key')!
    key.value = 'sk-test'
    key.dispatchEvent(new Event('input'))
    await nextTick()

    document.querySelector<HTMLElement>('.pw-save')!.click()
    await flushPromises()

    expect(mocks.putSecret).toHaveBeenCalledWith('llm.profiles.deepseek', 'sk-test')
    expect(mocks.saveModule).toHaveBeenCalledWith('llm')
    const saved = mocks.editable.value.llm.profiles.deepseek
    expect(saved.model).toBe('deepseek-chat')
    expect(saved.models).toEqual(['deepseek-chat', 'deepseek-reasoner'])
    expect(w.emitted('saved')?.[0]).toEqual(['deepseek'])
  })

  it('未填 key 不调用 putSecret', async () => {
    mountWizard()
    await openPreset()
    document.querySelector<HTMLElement>('.pw-save')!.click()
    await flushPromises()
    expect(mocks.putSecret).not.toHaveBeenCalled()
    expect(mocks.saveModule).toHaveBeenCalled()
  })

  it('编辑已有供应商：预填并集，保存保留 compat/voices/旧 model', async () => {
    const profiles = {
      openai: {
        provider: 'openai', endpoint: 'https://api.openai.com',
        model: 'gpt-4o-mini', models: ['gpt-4o'],
        compat: { stream_options: false }, voices: ['alloy'], language: 'en',
      },
    }
    mountWizard('openai', profiles)
    document.querySelector<HTMLElement>('.pw-next')!.click()
    await flushPromises()

    const rows = document.querySelectorAll('.mt-row input')
    expect(rows).toHaveLength(2)

    document.querySelector<HTMLElement>('.pw-save')!.click()
    await flushPromises()

    const saved = mocks.editable.value.llm.profiles.openai
    expect(saved.model).toBe('gpt-4o-mini')          // 旧 model 仍在列表中则保留
    expect(saved.models).toEqual(['gpt-4o-mini', 'gpt-4o'])
    expect(saved.compat).toEqual({ stream_options: false })
    expect(saved.voices).toEqual(['alloy'])
    expect(saved.language).toBe('en')
  })

  it('拉取失败显示错误且不清空已有表格', async () => {
    mocks.fetchModels.mockRejectedValue(new Error('403 Forbidden'))
    mountWizard()
    await openPreset()

    document.querySelector<HTMLElement>('.pw-fetch')!.click()
    await flushPromises()

    expect(document.body.textContent).toContain('403 Forbidden')
    expect(document.querySelectorAll('.mt-row')).toHaveLength(2)
  })
})

describe('ProviderWizard 编辑与错误处理（review 修复）', () => {
  it('编辑模式 ID 不符合新增正则时仍可进入第 2 步', async () => {
    const profiles = { 'My-Provider': { provider: 'openai', endpoint: 'https://x', model: 'm' } }
    mountWizard('My-Provider', profiles)
    expect(nextButton().disabled).toBe(false)
    nextButton().click()
    await flushPromises()
    expect(document.body.textContent).toContain('API Key')
  })

  it('编辑模式获取模型带上 profile name（服务端才能命中已存密钥）', async () => {
    mocks.fetchModels.mockResolvedValue({ ok: true, models: ['m'], count: 1 })
    const profiles = {
      openai: { provider: 'openai', endpoint: 'https://api.openai.com', model: 'm',
                api_key_env: 'OPENAI_KEY', models_path: '/v1/models' },
    }
    mountWizard('openai', profiles)
    nextButton().click()
    await flushPromises()
    document.querySelector<HTMLElement>('.pw-fetch')!.click()
    await flushPromises()

    const payload = mocks.fetchModels.mock.calls[0][1]
    expect(payload.name).toBe('openai')
    expect(payload.api_key_env).toBe('OPENAI_KEY')
    expect(payload.models_path).toBe('/v1/models')
  })

  it('编辑模式保存保留自定义 chat_path', async () => {
    const profiles = { openai: { provider: 'openai', endpoint: 'https://x', model: 'm',
                                 chat_path: '/custom/path', models: ['m'] } }
    mountWizard('openai', profiles)
    nextButton().click()
    await flushPromises()
    document.querySelector<HTMLElement>('.pw-save')!.click()
    await flushPromises()

    expect(mocks.editable.value.llm.profiles.openai.chat_path).toBe('/custom/path')
  })

  it('编辑 p1 时点不存在的预设，不会继承 p1 的字段', async () => {
    const profiles = { openai: { provider: 'openai', endpoint: 'https://x', model: 'm',
                                 models: ['m'], compat: { x: true }, voices: ['v'] } }
    mountWizard('openai', profiles)
    await openPreset()
    document.querySelector<HTMLElement>('.pw-save')!.click()
    await flushPromises()

    const created = mocks.editable.value.llm.profiles.deepseek
    expect(created.compat).toBeUndefined()
    expect(created.voices).toBeUndefined()
    expect(profiles.openai.compat).toEqual({ x: true })
  })

  it('首个供应商保存时自动设为 active', async () => {
    mountWizard(null, {})
    await openPreset()
    document.querySelector<HTMLElement>('.pw-save')!.click()
    await flushPromises()
    expect(mocks.editable.value.llm.active).toBe('deepseek')
  })

  it('putSecret 失败：提示且不关闭向导', async () => {
    mocks.putSecret.mockRejectedValueOnce(new Error('secret boom'))
    const w = mountWizard()
    await openPreset()
    const key = document.querySelector<HTMLInputElement>('.pw-key')!
    key.value = 'sk-x'
    key.dispatchEvent(new Event('input'))
    await nextTick()

    document.querySelector<HTMLElement>('.pw-save')!.click()
    await flushPromises()

    expect(mocks.notifyErr).toHaveBeenCalled()
    expect(w.emitted('saved')).toBeUndefined()
  })
})
