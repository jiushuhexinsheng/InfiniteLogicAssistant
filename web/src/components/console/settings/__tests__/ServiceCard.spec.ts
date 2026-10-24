// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../../../../api', () => ({
  api: { patchConfig: vi.fn(), getConfigFull: vi.fn(), getDetection: vi.fn() },
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

  /** profile.voices 同步进「音色」组合框的建议层（UiCombobox 替换原生 datalist）。
   *  profile.voices feeds the voice combobox suggestions (UiCombobox replaced the native datalist). */
  it('voices 进入音色组合框建议（聚焦弹出项目风格面板）', async () => {
    const w = mount(ServiceCard, { props: { section: ttsDef } })
    // 模型字段已移出 ServiceCard（由供应商向导维护），此处只剩 voice 组合框。
    // The model field moved out of ServiceCard (owned by the provider wizard); only voice remains.
    const combos = w.findAll('.ui-combo input')
    expect(combos.length, '仅 voice 组合框').toBe(1)
    // 按当前值定位 voice 输入（不依赖字段渲染顺序）。Locate the voice input by its
    // current value (no reliance on field render order).
    const voiceInput = combos.find(i => (i.element as HTMLInputElement).value === 'Chloe')
    expect(voiceInput, '应存在值为 Chloe 的组合框').toBeTruthy()
    await voiceInput!.trigger('focus')
    const opts = document.querySelectorAll('body > .ui-select-menu .ui-select-option')
    expect([...opts].some(o => o.textContent?.includes('Mia')), '建议面板应含 Mia').toBe(true)
  })
})

/** ASR section 定义（与 configDefs 单一来源一致）。ASR section def. */
const asrDef = sectionDefs.find(d => d.key === 'asr')!

/** ASR 段快照。**保留 tts 段**：本文件上方 TTS 用例挂载的组件不会 unmount，beforeEach
 *  换掉 editable 时它们会重渲染 —— 快照缺 tts 会让 `s.sec('tts')` 变 undefined 而抛错。
 *  ASR snapshot. Keeps the tts section: components mounted by the TTS cases above are not
 *  unmounted and re-render when editable changes — a tts-less snapshot would make
 *  `s.sec('tts')` undefined and throw. */
function asrSnapshot(mode = 'cloud', present = false) {
  return {
    ...structuredClone(snapshot()),
    asr: {
      active: 'a', api_key_set: { a: false },
      profiles: {
        a: { provider: 'openai', endpoint: 'https://x', model: 'm', language: 'zh',
             chat_path: '/v1/chat/completions', timeout: 30 },
      },
      mode, local_model: 'models/asr', local_model_present: present,
    },
  }
}

/**
 * ASR 模式已收口到「本地模型」页；API Profile 卡不再渲染三模式控件。
 * ASR mode moved to the 本地模型 page; the API Profile card no longer renders it.
 */
describe('ServiceCard（ASR 本地面板已收口）', () => {
  beforeEach(() => {
    editable.value = structuredClone(asrSnapshot()) as any
  })

  it('不再渲染三模式控件，提示去「本地模型」页', () => {
    const w = mount(ServiceCard, { props: { section: asrDef } })
    expect(w.find('.ui-segmented').exists()).toBe(false)
    expect(w.text()).toContain('本地模型')
    expect(w.text()).toContain('转写模式')
  })

  it('本地模型已就位 → 不显示警示', () => {
    editable.value = structuredClone(asrSnapshot('local', true)) as any
    const w = mount(ServiceCard, { props: { section: asrDef } })
    expect(w.text()).not.toContain('本地 ASR 模型未就位')
  })
})

/** 编辑对象与 active 分离后的回归：兼容区必须读写「编辑对象」，不能读 active。 */
describe('ServiceCard 编辑对象隔离', () => {
  beforeEach(() => {
    const snap: any = snapshot()
    snap.tts.api_key_set.p2 = false
    snap.tts.profiles.mimo.compat = { stream_options: true }
    snap.tts.profiles.p2 = {
      provider: 'openai', endpoint: 'https://b', model: 'x', voice: 'Bob', voices: ['Bob'],
      format: 'wav', chat_path: '/v1/audio/speech', timeout: 30, models: [],
      compat: { auth_header: 'api-key' },
    }
    editable.value = snap
  })

  it('编辑非 active profile：兼容行显示其自身值，改动只写它', async () => {
    const w = mount(ServiceCard, { props: { section: ttsDef } })
    const trigger = w.find('.cs-profrow .ui-select')
    await trigger.trigger('click')
    const opt = document.querySelector('.ui-select-option[data-value="p2"]') as HTMLElement
    opt.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await w.vm.$nextTick()

    const rows = w.findAll('.cr-row input')
    expect((rows[0].element as HTMLInputElement).value).toBe('auth_header')

    await rows[1].setValue('changed')

    expect((editable.value as any).tts.profiles.p2.compat.auth_header).toBe('changed')
    expect((editable.value as any).tts.profiles.mimo.compat).toEqual({ stream_options: true })
  })

  it('兼容值写回保持类型（false 仍是布尔）', async () => {
    const w = mount(ServiceCard, { props: { section: ttsDef } })
    const valueInput = w.findAll('.cr-row input')[1]
    await valueInput.setValue('false')

    expect((editable.value as any).tts.profiles.mimo.compat.stream_options).toBe(false)
  })
})
