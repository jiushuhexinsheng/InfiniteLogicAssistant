// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { speaking, spokenChars, speakText, stopSpeak, ttsSettings } from '../useTts'

/** 让异步播报链（fetch → blob → Audio.play）推进到创建 Audio。Advance the async
 *  playback chain (fetch → blob → Audio.play) until the Audio is created. */
const flush = () => new Promise((r) => setTimeout(r, 0))

describe('useTts speaking 信号（后端引擎）', () => {
  let audios: any[]

  beforeEach(() => {
    audios = []
    speaking.value = false
    spokenChars.value = 0
    ttsSettings.value.engine = 'local'
    ttsSettings.value.speakEnabled = true
    ;(globalThis as any).fetch = vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob(),
    }))
    ;(globalThis as any).Audio = class {
      onended: (() => void) | null = null
      onerror: (() => void) | null = null
      volume = 1
      src = ''
      play() { audios.push(this); return Promise.resolve() }
      pause() {}
      setSinkId() { return Promise.resolve() }
    }
    ;(globalThis as any).URL.createObjectURL = vi.fn(() => 'blob:fake')
    ;(globalThis as any).URL.revokeObjectURL = vi.fn()
  })

  it('播报开始置 true，onended 置 false', async () => {
    speakText('你好')
    expect(speaking.value).toBe(true)
    await flush()
    audios[0].onended?.()
    await flush()
    expect(speaking.value).toBe(false)
  })

  it('onerror 同样复位', async () => {
    speakText('你好')
    await flush()
    audios[0].onerror?.()
    await flush()
    expect(speaking.value).toBe(false)
  })

  it('stopSpeak 立即复位并作废迟到 onended', async () => {
    speakText('你好')
    expect(speaking.value).toBe(true)
    await flush()
    stopSpeak('ui')
    expect(speaking.value).toBe(false)
    audios[0].onended?.()            // 迟到回调。Late callback.
    expect(speaking.value).toBe(false) // 不得复活。Must not revive.
  })

  it('空文本不置 speaking', () => {
    speakText('')
    expect(speaking.value).toBe(false)
  })

  it('纯空白不置 speaking', () => {
    speakText('   ')
    expect(speaking.value).toBe(false)
  })

  it('spokenChars 累计已播出口文本', async () => {
    speakText('第一句话已经说完了。')
    expect(spokenChars.value).toBe(0)
    await flush()
    audios[0].onended?.()
    await flush()
    expect(spokenChars.value).toBe('第一句话已经说完了。'.length)
  })
})
