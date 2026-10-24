// @vitest-environment jsdom
/** 向导第 1 步：ID/URL 校验、重名提示、编辑模式 ID 只读。Wizard step 1 validation and edit mode.
 *  面板由 UiModal Teleport 到 body，故用 document 查询而不是 wrapper.find。 */
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ProviderWizard from '../ProviderWizard.vue'

const PROFILES = { openai: { provider: 'openai', endpoint: 'https://api.openai.com', model: 'gpt-4o-mini' } }

let lastWrapper: VueWrapper<any> | null = null

afterEach(async () => {
  lastWrapper?.unmount()
  lastWrapper = null
  await flushPromises()
})

function mountWizard(editingId: string | null = null) {
  lastWrapper = mount(ProviderWizard, {
    props: { modelValue: true, section: 'llm', editingId, profiles: PROFILES },
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
  return document.querySelector('.pw-next') as HTMLButtonElement
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
