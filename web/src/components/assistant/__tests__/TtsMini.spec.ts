// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

/** 可控的 /api/config 桩：tts_available / tts_voice / tts_model 由各测试设定。
 *  Controllable /api/config stub: tests set tts_available / tts_voice / tts_model. */
const configRef = { value: null as any }
vi.mock('../../../composables/useApi', () => ({
  useConfig: () => ({ config: configRef, initConfig: vi.fn(), refreshConfig: vi.fn() }),
}))

import TtsMini from '../TtsMini.vue'
import { ttsSettings, saveTts } from '../../../composables/assistant/useTts'

/**
 * 开始页语音设置迷你卡：引擎选择 + 角色选择 + 试听。
 *
 * 回归靶子：引擎选择复用 useTtsEngine 单例（与控制台语音合成卡1 同源），
 * 改动必须持久化并即时反映在 UI 上；角色选择按引擎切换控件形态。
 * 迁移后引擎选择由 UiSegmented 承载（.sg-item），角色选择由 VoiceSelect 承载。
 *
 * Start-page voice settings mini card: engine picker + voice selection + preview.
 * After migration the engine picker is UiSegmented (.sg-item), voice selection is VoiceSelect.
 */
describe('TtsMini（开始页语音设置卡）', () => {
  beforeEach(() => {
    ttsSettings.value.engine = 'browser'
    saveTts()
    configRef.value = { tts_available: true, tts_voice: 'Chloe' }
  })

  /** 卡片三要素齐全：引擎选择、角色选择、试听。All three essentials present. */
  it('渲染引擎选择、角色选择与试听', () => {
    const w = mount(TtsMini)
    expect(w.findAll('.sg-item').length).toBe(2)
    expect(w.text()).toContain('本地语音')
    expect(w.text()).toContain('API 语音')
    expect(w.find('.ui-select').exists()).toBe(true)   // 本地引擎 = 系统语音下拉（自绘触发器）
    expect(w.text()).toContain('角色')
    expect(w.text()).toContain('试听')
    // 无障碍语义随 UiSegmented 迁移保留。A11y semantics preserved via UiSegmented.
    expect(w.find('[role="radiogroup"]').exists()).toBe(true)
    expect(w.findAll('[role="radio"]').length).toBe(2)
  })

  /** 引擎切换：写入 localStorage 并切到 API 音色下拉（点开即选，非 datalist 输入框）。
   *  Engine switch persists and swaps to the API voice dropdown (open-to-pick, not a datalist input). */
  it('切换到 API 后角色选择变为音色下拉', async () => {
    const w = mount(TtsMini)
    await w.findAll('.sg-item')[1].trigger('click')
    expect(ttsSettings.value.engine).toBe('api')
    expect(localStorage.getItem('xluo.tts')).toContain('"engine":"api"')
    // API 分支带徽标且是 UiSelect（不再是 input+datalist）。API branch has the badge and is a UiSelect.
    expect(w.find('.vs-label em').exists()).toBe(true)
    expect(w.find('.voice-select .ui-select').exists()).toBe(true)
    expect(w.find('.ui-input').exists()).toBe(false)
    expect(w.findAll('.sg-item')[1].classes()).toContain('on')
  })

  /** API 音色候选含「默认音色」与后端默认 voice。API candidates include the default entry and backend voice. */
  it('API 音色下拉候选含默认项与后端默认音色', async () => {
    const w = mount(TtsMini)
    await w.findAll('.sg-item')[1].trigger('click')
    // 展开面板断言候选（选项在面板打开时才进 DOM）。Assert candidates after opening (options enter the DOM on open).
    await w.find('.voice-select .ui-select').trigger('click')
    const labels = [...document.querySelectorAll('.ui-select-option')].map(o => o.textContent?.trim())
    expect(labels.some(t => t?.includes('默认音色'))).toBe(true)
    expect(labels).toContain('Chloe')
  })

  /** 选了 API 但后端未配置：引导提示出现，但选择不被阻止。
   *  API chosen but backend unconfigured: guidance appears, selection still allowed. */
  it('API 未配置时显示引导但不禁用选择', async () => {
    configRef.value = { tts_available: false }
    const w = mount(TtsMini)
    await w.findAll('.sg-item')[1].trigger('click')
    expect(ttsSettings.value.engine).toBe('api')
    expect(w.text()).toContain('控制台「语音合成」')
    expect(w.findAll('.sg-item')[1].attributes('disabled')).toBeUndefined()
  })

  /** voiceclone 模型：角色由后端参考音频决定，前端不给选择控件。
   *  Voiceclone model: backend decides the voice; no picker rendered. */
  it('voiceclone 模型显示克隆提示而非选择控件', async () => {
    configRef.value = { tts_available: true, tts_model: 'mimo-v2.5-tts-voiceclone' }
    const w = mount(TtsMini)
    await w.findAll('.sg-item')[1].trigger('click')
    expect(w.find('.voice-select .ui-select').exists()).toBe(false)
    expect(w.find('.vs-clone').exists()).toBe(true)
    expect(w.text()).toContain('voice_ref')
  })
})
