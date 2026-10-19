// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * 流式语音麦克风控制：开启 → 建 WebSocket 流；关闭 → 停流；事件转发；麦克风错误。
 *
 * Streaming mic control: power on creates the WebSocket stream, power off stops it,
 * server events are forwarded, and mic errors surface.
 */

const mocks = vi.hoisted(() => ({
  handle: {
    start: vi.fn(async () => {}),
    stop: vi.fn(),
    send: vi.fn(),
    setMuted: vi.fn(),
    isRunning: () => true,
  },
  handleStreamEvent: vi.fn(async () => {}),
}))

vi.mock('../stream/streamClient', () => ({
  createVoiceStream: vi.fn(() => mocks.handle),
}))

vi.mock('../stream/streamFlow', () => ({ handleStreamEvent: mocks.handleStreamEvent }))

// 简化 DI 依赖：避免拉起真实聊天/TTS 网络层。
vi.mock('../../../api', () => ({ api: { stopTask: vi.fn(), callStop: vi.fn() }, streamUtter: vi.fn() }))
vi.mock('../useTts', async () => {
  const { ref } = await import('vue')
  return { speakAuto: vi.fn(), stopSpeak: vi.fn(), speaking: ref(false) }
})

import { state, wakeEnabled } from '../store'
import { st } from '../wake/orchState'
import { toggleWake, stopWake, describeMicError } from '../useWakeWord'

function stubBrowser() {
  // jsdom 没有 AudioContext / WebSocket；micControl 的能力守卫需要它们存在。
  // jsdom lacks AudioContext / WebSocket; micControl's capability guard requires them.
  ;(window as any).AudioContext = class {}
  ;(window as any).webkitAudioContext = (window as any).AudioContext
  ;(globalThis as any).WebSocket = class {}
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      enumerateDevices: vi.fn(async () => [{ kind: 'audioinput', deviceId: 'mic-1' }]),
    },
  })
}

describe('流式语音开关', () => {
  beforeEach(() => {
    stopWake()
    vi.clearAllMocks()
    mocks.handle.start.mockReset()
    mocks.handle.start.mockResolvedValue(undefined)
    stubBrowser()
    state.value = 'idle'
    wakeEnabled.value = false
  })

  it('关闭态开启 → 建流并落静待', async () => {
    const { createVoiceStream } = await import('../stream/streamClient')
    await toggleWake()
    expect(vi.mocked(createVoiceStream)).toHaveBeenCalledTimes(1)
    expect(mocks.handle.start).toHaveBeenCalledTimes(1)
    expect(wakeEnabled.value).toBe(true)
    expect(state.value).toBe('standby')
  })

  it('再次切换 → 停流并回关闭态', async () => {
    await toggleWake()
    await toggleWake()
    expect(mocks.handle.stop).toHaveBeenCalledTimes(1)
    expect(wakeEnabled.value).toBe(false)
    expect(state.value).toBe('idle')
  })

  it('服务端事件转发给 streamFlow', async () => {
    const { createVoiceStream } = await import('../stream/streamClient')
    await toggleWake()
    const opts = vi.mocked(createVoiceStream).mock.calls[0][0]
    opts.onEvent({ type: 'partial', text: '你好' })
    expect(mocks.handleStreamEvent).toHaveBeenCalledWith({ type: 'partial', text: '你好' })
  })

  it('取流失败 → 错误态 + 可见提示', async () => {
    mocks.handle.start.mockRejectedValueOnce(Object.assign(new Error('denied'), { name: 'NotAllowedError' }))
    await toggleWake()
    expect(state.value).toBe('error')
    expect(wakeEnabled.value).toBe(false)
  })

  it('stopWake 收掉麦克风流', async () => {
    await toggleWake()
    stopWake()
    expect(mocks.handle.stop).toHaveBeenCalled()
    expect(st.voiceStream).toBeNull()
  })

  it('describeMicError 给出可操作文案', () => {
    expect(describeMicError({ name: 'NotAllowedError' })).toContain('麦克风权限被拒绝')
    expect(describeMicError({ name: 'NotFoundError' })).toContain('未检测到可用麦克风')
  })
})
