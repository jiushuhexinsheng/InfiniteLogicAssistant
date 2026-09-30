// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

/** 可控的 /api/config 桩：tts_available 由各测试设定。
 *  Controllable /api/config stub: tests set tts_available. */
const configRef = { value: null as any }
vi.mock('../../../../composables/useApi', () => ({
  useConfig: () => ({ config: configRef, initConfig: vi.fn(), refreshConfig: vi.fn() }),
}))

import TtsEngineCard from '../TtsEngineCard.vue'
import { ttsSettings, saveTts } from '../../../../composables/assistant/useTts'

/**
 * 卡1：引擎大选择（第一眼看清本地 / API）+ 播报总开关 + 试听。
 *
 * 回归靶子：引擎选择是用户意图，**不因后端未配置而禁用 API 按钮** ——
 * 否则「未配置 → 不能选 API → 到不了卡2 的 API 配置卡」是死循环；
 * 选了 API 但后端未启用时给引导提示，播报运行时自动回退本地。
 * 迁移后引擎大选择由 UiRadioCard 承载（.rc-card）。
 *
 * Card 1: large engine picker (local vs API at first glance) + master switch + preview.
 */
describe('TtsEngineCard（引擎选择卡）', () => {
  beforeEach(() => {
    ttsSettings.value.engine = 'browser'
    saveTts()
    configRef.value = { tts_available: true }
  })

  /** 两枚大按钮都渲染且可点。Both large buttons render and are clickable. */
  it('渲染本地 / API 两枚引擎按钮', () => {
    const w = mount(TtsEngineCard)
    const btns = w.findAll('.rc-card')
    expect(btns.length).toBe(2)
    expect(btns[0].text()).toContain('本地语音')
    expect(btns[1].text()).toContain('API 语音')
    expect(btns[0].attributes('disabled')).toBeUndefined()
    expect(btns[1].attributes('disabled')).toBeUndefined()
    // 无障碍语义随 UiRadioCard 迁移保留。A11y semantics preserved via UiRadioCard.
    expect(w.find('[role="radiogroup"]').exists()).toBe(true)
  })

  /** 点击切换引擎并持久化。Clicking switches the engine and persists it. */
  it('点击 API 切换引擎并写入 localStorage', async () => {
    const w = mount(TtsEngineCard)
    await w.findAll('.rc-card')[1].trigger('click')
    expect(ttsSettings.value.engine).toBe('api')
    expect(localStorage.getItem('xluo.tts')).toContain('"engine":"api"')
    expect(w.findAll('.rc-card')[1].classes()).toContain('on')
  })

  /** 播报总开关与试听在卡1。Master switch and preview live in card 1. */
  it('包含播报总开关与试听按钮', () => {
    const w = mount(TtsEngineCard)
    expect(w.find('[aria-label="启用语音播报"]').exists()).toBe(true)
    expect(w.text()).toContain('试听')
  })

  /** 选 API 但后端未启用：按钮不禁用，给引导提示（否则配置卡不可达）。
   *  API chosen but backend off: button stays enabled with guidance (otherwise the config card is unreachable). */
  it('API 不可用时按钮仍可点，但显示引导提示', async () => {
    configRef.value = { tts_available: false }
    const w = mount(TtsEngineCard)
    const apiBtn = w.findAll('.rc-card')[1]
    expect(apiBtn.attributes('disabled')).toBeUndefined()

    await apiBtn.trigger('click')
    expect(ttsSettings.value.engine).toBe('api')
    expect(w.text()).toContain('后端 TTS 未启用')
    expect(w.text()).toContain('下方')
  })

  /** 未选 API 时不打扰。No hint when API is not selected. */
  it('本地引擎下不显示 API 引导提示', () => {
    configRef.value = { tts_available: false }
    const w = mount(TtsEngineCard)
    expect(w.text()).not.toContain('后端 TTS 未启用')
  })
})
