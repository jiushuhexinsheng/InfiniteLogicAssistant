import { describe, it, expect } from 'vitest'
// 引擎源码（IIFE 全局，非 ES 模块）—— 见 wakeEngineRestart.spec.ts 的说明。
// The engine's source (an IIFE global, not an ES module) — see wakeEngineRestart.spec.ts.
import engineSource from '../../../../public/lib/wake-word.js?raw'

/**
 * 多唤醒词匹配。
 *
 * 2026-09-13 起默认支持两个唤醒词（「衍衡」「洛吉斯」）。匹配全靠 Vosk 的中文小模型，
 * 而它对非高频字识别率低，所以每个字都要配同音字兜底 —— 这些用例钉住的就是「兜底有没有
 * 覆盖新词」，以及「换词之后旧词是否真的不再触发」（否则等于没换）。
 *
 * Multiple wake keywords. Two are supported by default (「衍衡」 and 「洛吉斯」). Matching runs
 * entirely on Vosk's small Chinese model, which has poor accuracy on infrequent characters, so
 * every character needs homophone fallbacks. These cases pin down that the fallbacks cover the new
 * keywords — and that the *old* keyword genuinely stops firing, which is the difference between
 * changing the wake word and merely adding one.
 */

/** 载入引擎（注入桩），返回 match 与 init。Load the engine with stubs; returns match and init. */
function loadEngine() {
  const recs: Array<Record<string, Array<(m: unknown) => void>>> = []
  const makeRec = () => {
    const h: Record<string, Array<(m: unknown) => void>> = {}
    recs.push(h)
    return {
      setWords: () => {},
      on: (ev: string, fn: (m: unknown) => void) => { (h[ev] ||= []).push(fn) },
      acceptWaveform: () => {},
      remove: () => {},
    }
  }
  const vosk = { createModel: async () => ({ ready: true, KaldiRecognizer: function () { return makeRec() } }) }
  const audioCtx = function () {
    return {
      sampleRate: 16000,
      createMediaStreamSource: () => ({ connect: () => {} }),
      createScriptProcessor: () => ({ connect: () => {}, disconnect: () => {}, onaudioprocess: null }),
      createGain: () => ({ gain: { value: 0 }, connect: () => {}, disconnect: () => {} }),
      destination: {},
      close: async () => {},
    }
  }
  const quiet = { log: () => {}, warn: () => {}, error: () => {} }
  return new Function('vosk', 'window', 'navigator', 'console',
    engineSource + '\nreturn WakeWordEngine')(
    vosk, { AudioContext: audioCtx },
    { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => {} }] }) } },
    quiet)
}

/** 初始化引擎并指定唤醒词。Init the engine with the given keywords. */
async function engineWith(keywords: string[]) {
  const engine = loadEngine()
  await engine.init({ modelPath: 'x', keywords, sensitivity: 0.5 })
  return engine
}

describe('多唤醒词匹配', () => {
  /** 两个唤醒词都要能唤醒（这是本次改动的目的）。Both keywords must wake the engine. */
  it('两个唤醒词都能命中', async () => {
    const e = await engineWith(['衍衡', '洛吉斯'])
    expect(e.match('衍衡')).toBe(true)
    expect(e.match('洛吉斯')).toBe(true)
  })

  /**
   * 旧唤醒词必须**不再**命中 —— 否则等于只是多支持一个词，没真正换掉。
   * The old keyword must **stop** matching; otherwise this only adds a keyword rather than
   * replacing the wake word.
   */
  it('旧唤醒词不再命中', async () => {
    const e = await engineWith(['衍衡', '洛吉斯'])
    expect(e.match('小逻小逻')).toBe(false)
  })

  /** 同音字兜底：Vosk 小模型对非高频字识别率低，近似音也要能唤醒。 */
  it('同音字变体可命中', async () => {
    const e = await engineWith(['衍衡', '洛吉斯'])
    // 衍衡：演/眼/严 + 横/恒
    expect(e.match('演横')).toBe(true)
    expect(e.match('严恒')).toBe(true)
    // 洛吉斯：罗/落 + 及/即 + 思/司
    expect(e.match('罗及思')).toBe(true)
    expect(e.match('落即司')).toBe(true)
  })

  /** 转写里的空格不应影响命中（Vosk 常按词切分吐空格）。Spaces from the transcript must not break a hit. */
  it('带空格的转写仍命中', async () => {
    const e = await engineWith(['衍衡', '洛吉斯'])
    expect(e.match('衍 衡')).toBe(true)
    expect(e.match('洛 吉 斯')).toBe(true)
  })

  /** 出现在长句里也应命中（用户常连说一句话）。A hit inside a longer sentence must still fire. */
  it('长句里出现也命中', async () => {
    const e = await engineWith(['衍衡', '洛吉斯'])
    expect(e.match('那个衍衡啊帮我查一下天气')).toBe(true)
  })

  /** 无关文本不能命中 —— 唤醒词最怕误触发。Unrelated text must not fire; false wakes are the main hazard. */
  it('无关文本不命中', async () => {
    const e = await engineWith(['衍衡', '洛吉斯'])
    for (const t of ['今天天气怎么样', '帮我打开浏览器', '这里没有唤醒词', '']) {
      expect(e.match(t), t).toBe(false)
    }
  })

  /** 单唤醒词配置仍然可用（配置成几个就认几个）。A single-keyword config still works. */
  it('只配一个词时只认这个词', async () => {
    const e = await engineWith(['衍衡'])
    expect(e.match('衍衡')).toBe(true)
    expect(e.match('洛吉斯')).toBe(false)
  })

  /** 兼容旧的单数 `keyword` 字段，避免老配置/老调用方静默失效。 */
  it('兼容旧的单数 keyword 字段', async () => {
    const engine = loadEngine()
    await engine.init({ modelPath: 'x', keyword: '衍衡', sensitivity: 0.5 })
    expect(engine.match('衍衡')).toBe(true)
    expect(engine.match('洛吉斯')).toBe(false)
  })
})
