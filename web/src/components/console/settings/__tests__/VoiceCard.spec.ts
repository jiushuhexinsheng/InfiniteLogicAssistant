// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../../../../api', () => ({
  api: { patchConfig: vi.fn(), getConfigFull: vi.fn(), getProviders: vi.fn() },
}))
// TTS 面板自带 SpeechSynthesis / TTS 接线，与本卡的断言无关，替换成空组件。
// The TTS panel carries its own speech-synthesis wiring, irrelevant to this card's assertions.
vi.mock('../../../assistant/TtsSettings.vue', () => ({ default: { template: '<div />' } }))

import { editable } from '../state'
import VoiceCard from '../VoiceCard.vue'

/**
 * 语音唤醒卡：唤醒词是**列表**，必须绑在 `keywords` 上。
 *
 * 回归靶子：这里曾绑定单数的 `keyword` —— 接口模型只有 `keywords`，于是输入框读到 undefined
 * （渲染成空框，看起来「没配唤醒词」），保存时 `_fold_legacy_keyword` 又以 `keywords` 为准把
 * 它丢掉，**唤醒词在界面上根本改不动**。
 *
 * Voice-wake card: the wake word is a **list** and must bind to `keywords`. The regression target:
 * this used to bind the singular `keyword`, which the API model does not have — the input read
 * undefined (an empty box that looks unconfigured) and on save `_fold_legacy_keyword` discarded it
 * because `keywords` wins, so the wake word could not be changed from the UI at all.
 */
function snapshot() {
  return {
    wake_word: { enabled: true, keywords: ['衍衡', '洛吉斯'], sensitivity: 0.5, model_path: '' },
    vad: {
      silence_threshold: 0.02, silence_duration_ms: 1500, max_duration_ms: 10000,
      answer_timeout_ms: 8000, min_speech_ms: 300, upload_throttle_ms: 500,
    },
  }
}

describe('VoiceCard', () => {
  beforeEach(() => {
    editable.value = structuredClone(snapshot()) as any
  })

  /** 每个唤醒词一行，值来自 keywords（不是空框）。One row per keyword, valued from `keywords`. */
  it('每个唤醒词渲染一行输入并带出当前值', () => {
    const w = mount(VoiceCard)
    const inputs = w.findAll('input.ui-input').map((i) => (i.element as HTMLInputElement).value)
    expect(inputs).toContain('衍衡')
    expect(inputs).toContain('洛吉斯')
  })

  /** 编辑某一行写回 keywords 的对应下标，且不会写出 `keyword` 这个不存在的字段。 */
  it('编辑唤醒词写回 keywords，不产生 keyword 字段', async () => {
    const w = mount(VoiceCard)
    const idx = w.findAll('input.ui-input').findIndex((i) => (i.element as HTMLInputElement).value === '衍衡')
    await w.findAll('input.ui-input')[idx].setValue('小逻')
    const ww = (editable.value as any).wake_word
    expect(ww.keywords).toEqual(['小逻', '洛吉斯'])
    expect(ww.keyword).toBeUndefined()   // 单数字段不该再出现。The singular field must not come back.
  })

  /** 新增/删除行直接改 keywords 列表。Add/remove rows edit the list itself. */
  it('新增与删除唤醒词改动 keywords 列表', async () => {
    const w = mount(VoiceCard)
    await w.findAll('button').find((b) => b.text().includes('新增唤醒词'))!.trigger('click')
    expect((editable.value as any).wake_word.keywords).toEqual(['衍衡', '洛吉斯', ''])

    await w.findAll('button').filter((b) => b.text() === '删除')[0].trigger('click')
    expect((editable.value as any).wake_word.keywords).toEqual(['洛吉斯', ''])
  })

  /** 只剩一个唤醒词时不得删除：删空等于唤醒永久失效（静默故障）。 */
  it('只剩一个唤醒词时删除按钮禁用', async () => {
    ;(editable.value as any).wake_word.keywords = ['衍衡']
    const w = mount(VoiceCard)
    const del = w.findAll('button').find((b) => b.text() === '删除')!
    expect(del.attributes('disabled')).toBeDefined()
  })

  /** 保存前剔除空唤醒词；全空则拒绝保存并明确提示（绝不静默存下一份唤不醒的配置）。 */
  it('空白唤醒词被剔除；全空时拒绝保存并提示', async () => {
    const w = mount(VoiceCard)
    const save = w.findAll('button').find((b) => b.text().includes('保存'))!
    ;(editable.value as any).wake_word.keywords = ['衍衡', '  ']
    await save.trigger('click')
    expect((editable.value as any).wake_word.keywords).toEqual(['衍衡'])

    ;(editable.value as any).wake_word.keywords = ['', ' ']
    await save.trigger('click')
    expect((editable.value as any).wake_word.keywords).toEqual(['', ' '])   // 未被存成空列表。Not saved as empty.
  })

  /** 成本控制的两个旋钮在设置页可调（文档把它们当降调用量的手段，界面不能只有一半）。 */
  it('两个成本旋钮可在设置页编辑', async () => {
    const w = mount(VoiceCard)
    const inputs = w.findAll('input.ui-input')
    expect(inputs.some((i) => (i.element as HTMLInputElement).value === '300')).toBe(true)
    expect(inputs.some((i) => (i.element as HTMLInputElement).value === '500')).toBe(true)
    await inputs.find((i) => (i.element as HTMLInputElement).value === '300')!.setValue('900')
    expect((editable.value as any).vad.min_speech_ms).toBe(900)
  })

  /** spec 要求：隐私边界必须写进设置页。Spec: the privacy boundary must be stated on the settings page. */
  it('写明云端上传的隐私边界', () => {
    const w = mount(VoiceCard)
    expect(w.text()).toContain('上传到云端 ASR')
    expect(w.text()).toContain('无论是否说出唤醒词')
  })
})
