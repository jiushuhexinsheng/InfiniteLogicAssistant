// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  api: {
    getConfigFull: vi.fn(),
    patchConfig: vi.fn(),
    getDetection: vi.fn(),
    getConfig: vi.fn(async () => ({ ok: true, llm_profile: 'p', llm_model: 'm' })),
    putSecret: vi.fn(),
    fetchModels: vi.fn(),
    getModels: vi.fn(async () => ({ ok: true, models: { vad: [], kws: [], asr: [], tts: [], llm: [] } })),
    refreshModels: vi.fn(async () => ({ ok: true, models: { vad: [], kws: [], asr: [], tts: [], llm: [] } })),
    getHardware: vi.fn(async () => ({
      ok: true,
      hardware: { providers: ['cpu'], cpu_count: 8, sherpa_version: '1.13.8', default_threads: 4 },
    })),
    getCapabilities: vi.fn(async () => ({
      ok: true,
      vad: { mode: 'local', present: true, ready: true, reason: '' },
      kws: { mode: 'local', present: true, ready: true, reason: '' },
      asr: { mode: 'local', present: true, ready: true, reason: '' },
      tts: { mode: 'local', present: true, ready: true, reason: '' },
    })),
  },
}))
// 播报面板自带 SpeechSynthesis 接线，与区块落位断言无关，替换成可识别的桩。
// The playback panel carries its own speech-synthesis wiring; stub it.
vi.mock('../../assistant/TtsSettings.vue', () => ({
  default: { template: '<div class="tts-settings-stub" />' },
}))

import { api } from '../../../api'
import { activeMenu, editable } from '../settings/state'
import { sectionDefs } from '../settings/configDefs'
import { ttsSettings, saveTts } from '../../../composables/assistant/useTts'
import ConsoleSettings from '../ConsoleSettings.vue'

/** 最小可编辑快照（语音页需要的四能力字段齐全）。
 *  Minimal editable snapshot with every field the voice page reads. */
function snapshot() {
  const svc = { active: 'p', profiles: { p: { provider: 'openai', endpoint: '', model: '' } }, api_key_set: { p: false } }
  return {
    llm: structuredClone(svc),
    asr: { ...structuredClone(svc), mode: 'local', local_model: 'models/asr/x', streaming: true,
           provider: 'cpu', device: 0, num_threads: 0, local_model_present: true },
    tts: { enabled: true, active: 'p', profiles: { p: { provider: 'openai', voices: [], format: 'wav' } },
           api_key_set: { p: false }, mode: 'local', local_model: 'models/tts/x', provider: 'cpu',
           device: 0, num_threads: 0, speaker: 0, speed: 1, lang: '' },
    wake_word: { enabled: true, keywords: ['衍衡'], sensitivity: 0.5, model_path: '' },
    vad: {
      mode: 'local', engine: 'ten-vad', model: 'models/vad/ten-vad.onnx', vad_threshold: 0.5,
      window_size: 0, provider: 'cpu', device: 0, num_threads: 0,
      silence_threshold: 0.02, silence_duration_ms: 1500, max_duration_ms: 10000,
      answer_timeout_ms: 8000, min_speech_ms: 300, upload_throttle_ms: 500,
      followup_window_ms: 6000, listen_idle_s: 180, barge_in: false,
    },
    kws: { enabled: true, mode: 'local', model_dir: 'models/kws/x', provider: 'cpu', device: 0,
           num_threads: 2, keywords_threshold: 0.25, keywords_score: 1 },
    streaming: { enabled: true, partial_interval_ms: 120, endpoint_silence_ms: 700,
                 max_utterance_ms: 15000 },
    hardware: { input_device: '', output_device: '', echo_cancellation: true,
                noise_suppression: true, auto_gain: true },
    permissions: { default_action: 'allow', tiers: { read: 'allow', write: 'allow', exec: 'allow' }, rules: [] },
    agent: {}, llm_client: {}, tools: {}, mcp: { servers: [] }, rag: {}, memory: {},
    server: { host: '127.0.0.1', port: 8520, open_browser: false, cors_origins: [], api_token_set: false },
  }
}

/** 切换语音页内部 Tab。Switch an internal tab of the voice page. */
async function openTab(w: ReturnType<typeof mount>, label: string) {
  const tab = w.findAll('.vs-tab').find(t => t.find('.vs-tab-zh').text() === label)
  expect(tab, `tab ${label}`).toBeTruthy()
  await tab!.trigger('click')
  await flushPromises()
}

describe('ConsoleSettings 语音统一页', () => {
  beforeEach(async () => {
    vi.mocked(api.getConfigFull).mockResolvedValue({ ok: true, editable: snapshot() } as any)
    editable.value = null
    activeMenu.value = 'voice'
    ttsSettings.value.engine = 'local'
    saveTts()
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { enumerateDevices: vi.fn(async () => []) },
    })
  })

  it('默认概览：六个 Tab + 语音链路状态条', async () => {
    const w = mount(ConsoleSettings)
    await flushPromises()
    expect(w.findAll('.vs-tab-zh').map(t => t.text())).toEqual([
      '概览', '唤醒', '识别', '合成', '硬件', '高级',
    ])
    expect(w.text()).toContain('语音总览')
    expect(w.findAll('.voice-tile').length).toBe(7)
    expect(w.text()).toContain('麦克风')
    expect(w.text()).toContain('VAD')
    expect(w.text()).toContain('TTS')
    expect(w.text()).not.toContain('一键本地')
  })

  it('唤醒 Tab 显示唤醒词', async () => {
    const w = mount(ConsoleSettings)
    await flushPromises()
    await openTab(w, '唤醒')
    expect(w.text()).toContain('唤醒词')
    expect(w.text()).not.toContain('语音总览')
  })

  it('识别 Tab 显示本地引擎；云端 Profile 在本地模式下折叠、展开后可见', async () => {
    const w = mount(ConsoleSettings)
    await flushPromises()
    await openTab(w, '识别')
    expect(w.text()).toContain('识别引擎（VAD / KWS / ASR）')
    expect(w.text()).not.toContain('ASR 语音识别（API Profile）')

    await w.find('.ud-head').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('ASR 语音识别（API Profile）')
  })

  it('合成 Tab 本地分支显示引擎选择 + 本地 TTS 卡', async () => {
    const w = mount(ConsoleSettings)
    await flushPromises()
    await openTab(w, '合成')
    expect(w.text()).toContain('语音引擎')
    expect(w.find('.ui-radio-cards').exists()).toBe(true)
    expect(w.text()).toContain('本地 TTS（Kokoro）')
    expect(w.find('.tts-settings-stub').exists()).toBe(false)
  })

  it('合成 Tab API 分支显示后端配置与新增字段', async () => {
    ttsSettings.value.engine = 'api'
    saveTts()
    const w = mount(ConsoleSettings)
    await flushPromises()
    await openTab(w, '合成')
    expect(w.text()).toContain('TTS 语音合成')
    expect(w.text()).toContain('参考音频（voiceclone）')
    expect(w.text()).toContain('音色列表（下拉候选）')
    expect(w.find('.tts-settings-stub').exists()).toBe(true)
  })

  it('识别页：单保存提交识别四段，云端配置在本地模式下默认折叠', async () => {
    vi.mocked(api.patchConfig).mockResolvedValue({ ok: true, restart_required: false } as any)
    const w = mount(ConsoleSettings)
    await flushPromises()
    await openTab(w, '识别')

    expect(w.text()).toContain('保存识别配置')
    expect(w.text()).not.toContain('ASR 语音识别（API Profile）')

    vi.mocked(api.patchConfig).mockClear()
    await w.find('.vs-save-recognition').trigger('click')
    await flushPromises()

    expect(api.patchConfig).toHaveBeenCalledTimes(1)
    const body = vi.mocked(api.patchConfig).mock.calls[0][0] as Record<string, any>
    expect(body.vad).toBeTruthy()
    expect(body.kws).toBeTruthy()
    expect(body.asr).toBeTruthy()
    expect(body.streaming).toBeTruthy()
  })

  it('editable 未加载时一张卡都不渲染且不抛错', async () => {
    vi.mocked(api.getConfigFull).mockReturnValue(new Promise(() => {}) as any)
    editable.value = null
    activeMenu.value = 'llm'
    const w = mount(ConsoleSettings)
    await flushPromises()
    expect(w.findAll('.cs-card').length).toBe(0)
    expect(w.find('.cs-menu').exists()).toBe(true)
  })
})

describe('ConsoleSettings 大模型页', () => {
  beforeEach(async () => {
    const snap = snapshot()
    vi.mocked(api.getConfigFull).mockResolvedValue({ ok: true, editable: snap } as any)
    vi.mocked(api.patchConfig).mockResolvedValue({ ok: true, restart_required: false } as any)
    vi.mocked(api.putSecret).mockResolvedValue({ ok: true, set: false, path: '' } as any)
    editable.value = null
    activeMenu.value = 'llm'
  })

  it('供应商列表可见；模型输入与「获取模型」从卡片移除', async () => {
    const w = mount(ConsoleSettings)
    await flushPromises()

    expect(w.find('.pr-row').exists()).toBe(true)
    expect(w.text()).toContain('模型供应商')
    expect(w.find('.cs-models').exists()).toBe(true)
    expect(w.find('.det-dot').exists()).toBe(true)
  })

  it('三段的字段定义都不再包含 model', () => {
    for (const def of sectionDefs) expect(def.fields).not.toContain('model')
  })

  it('设为当前后刷新全局配置（顶栏模型同步）', async () => {
    const snap: any = snapshot()
    snap.llm.profiles.p2 = { provider: 'openai', endpoint: 'https://b', model: 'm2' }
    snap.llm.api_key_set.p2 = false
    vi.mocked(api.getConfigFull).mockResolvedValue({ ok: true, editable: snap } as any)
    vi.mocked(api.getConfig).mockClear()

    const w = mount(ConsoleSettings)
    await flushPromises()

    await w.find('.pr-activate').trigger('click')
    await flushPromises()

    expect(api.patchConfig).toHaveBeenCalled()
    expect(api.getConfig).toHaveBeenCalled()
  })

  it('删除供应商：先存配置，再用空值清理密钥', async () => {
    const w = mount(ConsoleSettings)
    await flushPromises()

    await w.find('.pr-del').trigger('click')
    const confirm = [...document.querySelectorAll('.ui-modal .ui-btn')]
      .find(b => b.textContent?.includes('删除')) as HTMLElement
    confirm.click()
    await flushPromises()

    expect(api.patchConfig).toHaveBeenCalled()
    expect(api.putSecret).toHaveBeenCalledWith('llm.profiles.p', '')
  })
})
