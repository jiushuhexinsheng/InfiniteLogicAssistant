import { beforeEach, describe, expect, it, vi } from 'vitest'
import { speaking, speakText, ttsSettings } from '../useTts'

/**
 * 播报完成信号：门控必须覆盖整个播报时长，不是调用那一刻。
 * Speech completion signal: gating must span the whole utterance, not the call instant.
 */
describe('useTts speaking 信号', () => {
  let utterances: any[]

  beforeEach(() => {
    utterances = []
    speaking.value = false
    ttsSettings.value.engine = 'browser'
    ;(globalThis as any).window = globalThis
    // SpeechSynthesisUtterance 桩：记录实例供测试手动触发 onend。
    // Stub that records instances so the test can fire onend manually.
    ;(globalThis as any).SpeechSynthesisUtterance = class {
      text: string
      onend: (() => void) | null = null
      onerror: (() => void) | null = null
      volume = 1
      rate = 1
      pitch = 1
      lang = ''
      voice: any = null
      constructor(text: string) { this.text = text; utterances.push(this) }
    }
    // getVoices 必须给 —— resolveVoice() 会调它，缺了会抛异常被 speakBrowser 的外层
    // try/catch 吞掉，表现为 speaking 静默不置位（排查时踩过）。
    // getVoices is required: resolveVoice() calls it, and without it the throw is swallowed
    // by speakBrowser's outer try/catch, leaving speaking silently unset.
    ;(globalThis as any).speechSynthesis = { cancel: vi.fn(), speak: vi.fn(), getVoices: () => [] }
    ;(globalThis as any).requestAnimationFrame = (fn: () => void) => { fn(); return 0 }
  })

  /** 播报开始即置 true，onend 置 false。speaking turns true when playback starts and onend clears it. */
  it('播报开始置 true，onend 置 false', () => {
    speakText('你好')
    expect(speaking.value).toBe(true)
    utterances[0].onend?.()
    expect(speaking.value).toBe(false)
  })

  /** onerror 也要复位，否则一次失败会让门控永久关闭。onerror must reset too, or one failure would gate listening off forever. */
  it('onerror 同样复位', () => {
    speakText('你好')
    utterances[0].onerror?.()
    expect(speaking.value).toBe(false)
  })

  /** 代际计数：连续两次播报时，第一次迟到的 onend 不得把第二次的 speaking 提前置 false。
   *  Generation counter: with back-to-back utterances, a late onend from the first must
   *  not clear the second's speaking flag early. */
  it('旧播报迟到的 onend 不提前复位', () => {
    speakText('第一句')
    speakText('第二句')
    expect(speaking.value).toBe(true)
    utterances[0].onend?.()            // 第一句的 onend 迟到
    expect(speaking.value).toBe(true)  // 第二句仍在播
    utterances[1].onend?.()
    expect(speaking.value).toBe(false)
  })

  /** 空文本直接返回，不置 speaking。Empty text returns early and leaves speaking false. */
  it('空文本不置 speaking', () => {
    speakText('')
    expect(speaking.value).toBe(false)
  })
})
