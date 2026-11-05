import { describe, it, expect, vi, afterEach } from 'vitest'
import { state, callActive, pendingQuestion } from '../store'
import { st, currentGate, syncStreamGate } from '../wake/orchState'
import type { VoiceStreamHandle } from '../stream/streamClient'

/**
 * 上传闸门上下文：唤醒待命 = wake（KWS 未命中不上云），
 * 通话/待答/指令窗/续聊 = open（免唤醒，不能被 KWS 拦截）。
 *
 * Upload-gate context: waiting for the wake word = wake (KWS miss never uploads);
 * call / answer / command window / follow-up = open (wake-free, never gated).
 */
function reset() {
  state.value = 'listening'
  callActive.value = false
  pendingQuestion.value = null
  st.awaitingCommand = false
  st.followupActive = false
  st.voiceStream = null
}

afterEach(reset)

describe('上传闸门上下文', () => {
  it('默认聆听/静待使用 wake 闸门', () => {
    state.value = 'standby'
    expect(currentGate()).toBe('wake')
  })

  it('通话模式使用 open', () => {
    callActive.value = true
    expect(currentGate()).toBe('open')
  })

  it('待答问题使用 open', () => {
    pendingQuestion.value = { id: 'q1', question: '继续吗', options: [] } as never
    expect(currentGate()).toBe('open')
  })

  it('指令窗使用 open', () => {
    st.awaitingCommand = true
    expect(currentGate()).toBe('open')
  })

  it('续聊窗口在 transcribing 中间态仍保持 open', () => {
    st.followupActive = true
    state.value = 'transcribing'
    expect(currentGate()).toBe('open')
  })

  it('syncStreamGate 把当前闸门推给连接', () => {
    const setGate = vi.fn()
    st.voiceStream = { setGate } as unknown as VoiceStreamHandle
    callActive.value = true
    syncStreamGate()
    expect(setGate).toHaveBeenCalledWith('open')
  })
})
