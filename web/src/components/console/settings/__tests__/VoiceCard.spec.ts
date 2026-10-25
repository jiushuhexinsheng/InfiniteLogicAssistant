// @vitest-environment jsdom
/**
 * 唤醒页：唤醒词列表回归 + 改版后的 KWS 状态、灵敏度归位、隐私折叠。
 * Wake page: keyword-list regressions plus the redesigned KWS status, sensitivity
 * relocation and collapsible privacy note.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../../api', () => ({
  api: { patchConfig: vi.fn(), getConfigFull: vi.fn() },
}))
vi.mock('../../../../composables/useVoiceModuleStatus', () => ({
  useVoiceModuleStatus: () => ({
    status: {
      value: {
        kws: { mode: 'local', present: true, ready: true, reason: '', model_dir: 'models/kws/zipformer-3.3M' },
      },
    },
  }),
}))

import { editable } from '../state'
import VoiceCard from '../VoiceCard.vue'

/**
 * 唤醒词是**列表**，必须绑在 `keywords` 上。
 * The wake word is a list and must bind to `keywords` (the singular field does not exist).
 */
function snapshot() {
  return {
    wake_word: { enabled: true, keywords: ['衍衡', '洛吉斯'], sensitivity: 0.5, model_path: '' },
    kws: {
      mode: 'local', model_dir: 'models/kws/zipformer-3.3M',
      keywords_threshold: 0.25, keywords_score: 1,
    },
    vad: {
      silence_threshold: 0.02, silence_duration_ms: 1500, max_duration_ms: 10000,
      answer_timeout_ms: 8000, min_speech_ms: 300, upload_throttle_ms: 500,
      followup_window_ms: 6000, listen_idle_s: 180, barge_in: false,
    },
    asr: { mode: 'cloud' },
  }
}

describe('VoiceCard', () => {
  beforeEach(() => {
    editable.value = structuredClone(snapshot()) as any
  })

  it('每个唤醒词渲染一行输入并带出当前值', () => {
    const w = mount(VoiceCard)
    const inputs = w.findAll('input.ui-input').map((i) => (i.element as HTMLInputElement).value)
    expect(inputs).toContain('衍衡')
    expect(inputs).toContain('洛吉斯')
  })

  it('编辑唤醒词写回 keywords，不产生 keyword 字段', async () => {
    const w = mount(VoiceCard)
    const idx = w.findAll('input.ui-input').findIndex((i) => (i.element as HTMLInputElement).value === '衍衡')
    await w.findAll('input.ui-input')[idx].setValue('燕恒')
    const ww = (editable.value as any).wake_word
    expect(ww.keywords).toEqual(['燕恒', '洛吉斯'])
    expect(ww.keyword).toBeUndefined()
  })

  it('新增与删除唤醒词改动 keywords 列表', async () => {
    const w = mount(VoiceCard)
    await w.findAll('button').find((b) => b.text().includes('新增唤醒词'))!.trigger('click')
    expect((editable.value as any).wake_word.keywords).toEqual(['衍衡', '洛吉斯', ''])

    await w.findAll('button').filter((b) => b.text().includes('删除'))[0].trigger('click')
    expect((editable.value as any).wake_word.keywords).toEqual(['洛吉斯', ''])
  })

  it('只剩一个唤醒词时删除按钮禁用', () => {
    ;(editable.value as any).wake_word.keywords = ['衍衡']
    const w = mount(VoiceCard)
    const del = w.findAll('button').find((b) => b.text().includes('删除'))!
    expect(del.attributes('disabled')).toBeDefined()
  })

  it('空白唤醒词被剔除；全空时拒绝保存', async () => {
    const w = mount(VoiceCard)
    const save = w.findAll('button').find((b) => b.text().includes('保存'))!
    ;(editable.value as any).wake_word.keywords = ['衍衡', '  ']
    await save.trigger('click')
    expect((editable.value as any).wake_word.keywords).toEqual(['衍衡'])

    ;(editable.value as any).wake_word.keywords = ['', ' ']
    await save.trigger('click')
    expect((editable.value as any).wake_word.keywords).toEqual(['', ' '])
  })

  it('标题为「唤醒与交互」，灵敏度不再出现在本页', () => {
    const w = mount(VoiceCard)
    expect(w.text()).toContain('唤醒与交互')
    expect(w.text()).not.toContain('灵敏度（0-1）')
  })

  it('显示 KWS 状态与阈值，并可跳转识别页', async () => {
    const w = mount(VoiceCard)
    const status = w.find('.wk-status')
    expect(status.text()).toContain('本地 KWS')
    expect(status.text()).toContain('0.25')

    await w.find('.wk-adjust').trigger('click')
    expect(w.emitted('navigate')?.[0]).toEqual(['recognition'])
  })

  it('写明云端上传的隐私边界（折叠态展开后）', async () => {
    const w = mount(VoiceCard)
    expect(w.text()).not.toContain('无论是否说出唤醒词')

    await w.find('.ud-head').trigger('click')
    await flushPromises()

    const t = w.text()
    expect(t).toContain('ASR 服务商')
    expect(t).toContain('无论是否说出唤醒词')
    expect(t).toContain('音频不出本机')
    expect(t).not.toContain('KWS 闸门')
    expect(t).not.toContain('云端/自动模式')
  })

  it('answer_timeout_ms 的 label 反映指令窗语义', () => {
    const w = mount(VoiceCard)
    const t = w.text()
    expect(t).not.toContain('等待回答超时')
    expect(t).toContain('唤醒后等指令窗（ms）')
  })

  it('不再内嵌播报设置面板', () => {
    const w = mount(VoiceCard)
    expect(w.find('.tts-settings').exists()).toBe(false)
  })
})
