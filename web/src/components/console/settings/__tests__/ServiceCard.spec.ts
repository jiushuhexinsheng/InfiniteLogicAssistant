// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../../../../api', () => ({
  api: { patchConfig: vi.fn(), getConfigFull: vi.fn(), getProviders: vi.fn(), getDetection: vi.fn() },
}))

import { editable } from '../state'
import ServiceCard from '../ServiceCard.vue'
import { sectionDefs } from '../configDefs'

/** TTS section 定义（与 configDefs 单一来源一致）。TTS section def (single source of truth: configDefs). */
const ttsDef = sectionDefs.find(d => d.key === 'tts')!

/** 可编辑快照（tts 段）。Editable snapshot (tts section). */
function snapshot() {
  return {
    tts: {
      enabled: true,
      active: 'mimo',
      api_key_set: { mimo: true },
      profiles: {
        mimo: {
          provider: 'openai', endpoint: 'https://api.xiaomimimo.com',
          model: 'mimo-v2.5-tts', voice: 'Chloe', voices: ['Chloe', 'Mia'],
          format: 'mp3', voice_ref: '', chat_path: '/v1/chat/completions',
          timeout: 30, models: [],
        },
      },
    },
  }
}

/**
 * ServiceCard 语音合成扩展：slot 落位、voices 列表编辑、format 下拉。
 *
 * 回归靶子：播报设置面板（TtsSettings）从「语音唤醒」卡迁入「语音合成」卡，依赖本卡
 * 提供 slot；format 曾是自由文本（后端是 wav/mp3/pcm16 三值字面量）；voices 此前无 UI。
 *
 * ServiceCard TTS extensions: slot placement, voices list editing, format dropdown.
 */
describe('ServiceCard（语音合成扩展）', () => {
  beforeEach(() => {
    editable.value = structuredClone(snapshot()) as any
  })

  /** slot 渲染：TtsSettings 即通过它挂进卡片。Slot renders: TtsSettings mounts through it. */
  it('渲染默认 slot（播报面板的挂载点）', () => {
    const w = mount(ServiceCard, {
      props: { section: ttsDef },
      slots: { default: '<div class="tts-stub" />' },
    })
    expect(w.find('.tts-stub').exists()).toBe(true)
  })

  /** format 必须是三值下拉且改动写回 profile（自绘面板：点开触发器 → 点选项）。
   *  Format must be a three-value select that writes back (custom panel: open trigger → pick option). */
  it('format 为 wav/mp3/pcm16 下拉，改动写回 profile', async () => {
    const w = mount(ServiceCard, { props: { section: ttsDef } })
    // format 当前值 mp3（snapshot），用 data-value 定位触发器。
    // Current format is mp3 (snapshot); locate the trigger via data-value.
    const trigger = w.find('.ui-select[data-value="mp3"]')
    expect(trigger.exists(), '应存在 format 触发器').toBe(true)
    await trigger.trigger('click')
    // 弹层 Teleport 到 body，需从 document 取。Panel is teleported to body; read from document.
    const opt = document.querySelector('.ui-select-option[data-value="wav"]')
    expect(opt, '面板应含 wav 选项').toBeTruthy()
    ;(opt as HTMLElement).dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect((editable.value as any).tts.profiles.mimo.format).toBe('wav')
  })

  /** voices 逐行渲染，新增/删除直接改 profile.voices。Rows render; add/remove edits profile.voices. */
  it('voices 列表逐行渲染，可新增与删除', async () => {
    const w = mount(ServiceCard, { props: { section: ttsDef } })
    expect(w.findAll('.cs-voicerow').length).toBe(2)

    await w.findAll('button').find(b => b.text().includes('新增音色'))!.trigger('click')
    expect((editable.value as any).tts.profiles.mimo.voices).toEqual(['Chloe', 'Mia', ''])

    // 行内删除按钮（区别于 Profile 行的同名按钮）。In-row delete (distinct from the Profile-row button of the same name).
    await w.findAll('.cs-voicerow')[0].find('button')!.trigger('click')
    expect((editable.value as any).tts.profiles.mimo.voices).toEqual(['Mia', ''])
  })

  /** voice_ref 字段露出（voiceclone 必需，此前只能手改 config.yaml）。voice_ref exposed (required for voiceclone; previously config.yaml only). */
  it('露出参考音频（voice_ref）字段', () => {
    const w = mount(ServiceCard, { props: { section: ttsDef } })
    expect(w.text()).toContain('参考音频（voiceclone）')
  })

  /** profile.voices 同步进「音色」输入框的 datalist。profile.voices feeds the voice input's datalist. */
  it('voices 进入音色输入框的 datalist', () => {
    const w = mount(ServiceCard, { props: { section: ttsDef } })
    const dl = w.find('#dl-tts-voice')
    expect(dl.exists()).toBe(true)
    const values = dl.findAll('option').map(o => o.attributes('value'))
    expect(values).toContain('Mia')
  })
})
