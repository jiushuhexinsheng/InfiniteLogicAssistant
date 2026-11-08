// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('../../../composables/useAssistant', () => ({
  useAssistant: () => ({
    state: ref('idle'),
    visual: ref({ icon: 'wave' }),
    expanded: ref(false),
    wakeEnabled: ref(false),
    wakeHint: ref('「衍衡」'),
    toggleWake: vi.fn(),
  }),
}))
vi.mock('../../../composables/useConsole', () => ({
  useConsole: () => ({ activeTab: ref('start') }),
}))

import OrbHero from '../OrbHero.vue'
import { activeMenu } from '../../console/settings/state'
import { activeVoiceTab } from '../../console/settings/state'

/**
 * 起始页「语音设置」入口（docs/designs/10 4.3）。
 * 背景：按钮写死 `activeMenu = 'tts'`，而设置菜单只有 llm/voice/permissions/advanced ——
 * 落页右侧空白。修复后必须落到「语音」菜单，并直达「合成」Tab。
 *
 * Start-page "voice settings" entry (docs/designs/10 4.3). The button used to set
 * `activeMenu = 'tts'`, which no settings menu matches, so the destination rendered blank.
 * It must land on the 语音 menu and open the 合成 tab.
 */
describe('OrbHero 语音设置入口', () => {
  beforeEach(() => {
    activeMenu.value = 'llm'
    activeVoiceTab.value = 'overview'
    push.mockClear()
  })

  it('点击「语音设置」落到 voice 菜单并直达合成 Tab', async () => {
    const w = mount(OrbHero)
    const btn = w.findAll('button').find(b => b.text().includes('语音设置'))
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(activeMenu.value).toBe('voice')
    expect(activeVoiceTab.value).toBe('synthesis')
    expect(push).toHaveBeenCalledWith('/console')
  })
})
