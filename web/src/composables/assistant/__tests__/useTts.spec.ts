import { beforeEach, describe, expect, it, vi } from 'vitest'
import { speaking, spokenChars, speakText, stopSpeak, ttsSettings } from '../useTts'

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

  /** 纯空白同样不入队（切句后为空）。Whitespace-only text enqueues nothing either. */
  it('纯空白不置 speaking', () => {
    speakText('   ')
    expect(speaking.value).toBe(false)
  })
})

/** 句级队列：逐句播放、stopSpeak 打断、spokenChars 计数。
 *  Sentence queue: sequential playback, stopSpeak interruption, spokenChars. */
describe('useTts 句级队列与打断', () => {
  let utterances: any[]

  beforeEach(() => {
    utterances = []
    speaking.value = false
    ttsSettings.value.engine = 'browser'
    ;(globalThis as any).window = globalThis
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
    ;(globalThis as any).speechSynthesis = { cancel: vi.fn(), speak: vi.fn(), getVoices: () => [] }
    ;(globalThis as any).requestAnimationFrame = (fn: () => void) => { fn(); return 0 }
  })

  /** 两句文本切队后逐句播：第一句 onend 才起第二句，全完才复位 speaking。
   *  Two sentences play sequentially: the second starts only after the first ends,
   *  and speaking clears only when all are done. */
  it('多句按序播放', async () => {
    speakText('第一句话已经说完了。明天会继续下雨吗？')
    expect(utterances.length).toBe(1)  // 第二句在队列里等。Second sentence waits in queue.
    expect(utterances[0].text).toContain('第一句话')
    utterances[0].onend?.()
    await Promise.resolve()            // 泵在微任务里推进。Pump advances in a microtask.
    expect(utterances.length).toBe(2)
    expect(utterances[1].text).toContain('明天会继续')
    expect(speaking.value).toBe(true)   // 还没完。Not done yet.
    utterances[1].onend?.()
    expect(speaking.value).toBe(false)
  })

  /** stopSpeak 立即复位并作废迟到回调（打断白名单的执行体）。
   *  stopSpeak resets immediately and voids late callbacks (the whitelist's mechanism). */
  it('stopSpeak 立即停止并作废迟到 onend', () => {
    speakText('第一句话已经说完了。明天会继续下雨吗？')
    expect(speaking.value).toBe(true)
    stopSpeak('ui')
    expect(speaking.value).toBe(false)
    expect((globalThis as any).speechSynthesis.cancel).toHaveBeenCalled()
    utterances[0].onend?.()            // 迟到回调。Late callback.
    expect(speaking.value).toBe(false) // 不得复活。Must not revive.
  })

  /** 新播报替换旧播报且不叠播（runTurn 接线的等价物）：旧句被 cancel、新句独播。
   *  A new broadcast replaces the old without overlap (equivalent of runTurn's
   *  wiring): the old utterance is cancelled, only the new one plays. */
  it('新播报替换旧播报且不叠播', () => {
    speakText('第一句话已经说完了。')
    speakText('第二句话已经说完了。')
    expect((globalThis as any).speechSynthesis.cancel).toHaveBeenCalled()
    expect(utterances.length).toBe(2)   // 每轮各起一支 utter。Each round starts its own.
    utterances[0].onend?.()             // 旧句迟到结束不得复位新轮。Late end must not clear.
    expect(speaking.value).toBe(true)
    utterances[1].onend?.()
    expect(speaking.value).toBe(false)
  })

  /** spokenChars 只累计真正播完的句子（barge-in 前缀计数的基础）。
   *  spokenChars only counts fully played sentences (basis of the barge-in prefix count). */
  it('spokenChars 累计已播出口文本', async () => {
    speakText('第一句话已经说完了。')
    expect(spokenChars.value).toBe(0)   // 未播完不计。Not counted until done.
    utterances[0].onend?.()
    await Promise.resolve()             // 累计发生在泵的微任务里。Accumulation happens in the pump's microtask.
    expect(spokenChars.value).toBe('第一句话已经说完了。'.length)
  })

  /** 打断不产生上下文污染（docs/designs/02 §3.5 守则）：store 消息不受影响。
   *  Interrupt pollutes no context (docs/designs/02 §3.5): store messages unaffected. */
  it('stopSpeak 不修改会话消息', async () => {
    const store = await import('../store')
    const before = JSON.stringify(store.messages.value)
    speakText('第一句话已经说完了。')
    stopSpeak('ui')
    expect(JSON.stringify(store.messages.value)).toBe(before)
  })
})
