import { describe, it, expect, vi } from 'vitest'
// 静态脚本的源码（IIFE 全局，非 ES 模块）—— 用 Vite 的 ?raw 引入后注入桩执行。
// The static script's source (an IIFE global, not an ES module), pulled in via Vite's ?raw
// and executed with injected stubs.
import engineSource from '../../../../public/lib/wake-word.js?raw'

/**
 * 唤醒引擎重启后回调必须仍在。
 *
 * 为什么要测这个：`useWakeWord.ts` 的播报结束分支按「start() 只重建流与 recognizer、
 * 不碰回调」的约定，用**无参** `eng.start()` 恢复监听。若引擎在无参启动时把回调清成
 * null，唤醒词会被照常识别（日志照打 `[WW] WAKE!`），但应用层毫无反应 —— 表现为
 * 「第一次唤醒能用，之后再也唤不醒」的静默失败。端到端实测复现过：引擎在 7.2s、
 * 23.9s、56.6s 三次听见唤醒词，应用层只在 7.2s 响应了一次。
 *
 * The wake engine's callbacks must survive a restart. The post-playback branch in
 * `useWakeWord.ts` relies on the contract that "start() only rebuilds the stream and
 * recognizer and leaves the callbacks alone", calling `eng.start()` with no arguments to
 * resume. If the engine nulls the callbacks on an argument-less start, the wake word is still
 * recognized (the engine even logs `[WW] WAKE!`) while the app does nothing — presenting as
 * "the first wake works, every later one does not". Reproduced end to end: the engine heard
 * the wake word at 7.2s, 23.9s and 56.6s while the app responded only at 7.2s.
 */

/** 一次 KaldiRecognizer 创建所捕获的事件处理器。Handler set captured from one KaldiRecognizer. */
type Handlers = Record<string, Array<(msg: unknown) => void>>

/**
 * 加载引擎并注入最小桩。
 * Load the engine with minimal stubs.
 *
 * @returns 引擎实例、捕获到的处理器集合、以及触发一次唤醒的辅助函数。
 *   The engine, the captured handler sets, and a helper that fires a wake.
 */
function loadEngine(warn?: (m: string) => void) {
  const recs: Handlers[] = []
  const makeRec = () => {
    const h: Handlers = {}
    recs.push(h)
    return {
      setWords: () => {},
      on: (ev: string, fn: (msg: unknown) => void) => { (h[ev] ||= []).push(fn) },
      acceptWaveform: () => {},
      remove: () => {},
    }
  }

  const vosk = {
    createModel: async () => ({ ready: true, KaldiRecognizer: function () { return makeRec() } }),
  }
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
  const navigatorStub = {
    mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => {} }] }) },
  }
  const consoleStub = {
    log: () => {},
    warn: (m: string) => { if (warn) warn(String(m)) },
    error: () => {},
  }

  const engine = new Function('vosk', 'window', 'navigator', 'console',
    engineSource + '\nreturn WakeWordEngine')(
    vosk, { AudioContext: audioCtx }, navigatorStub, consoleStub)

  /** 让最近一次创建的 recognizer 收到一条 partial 结果（模拟听见唤醒词）。 */
  const fireWake = (text = '小逻小逻') => {
    const set = recs[recs.length - 1]
    set.partialresult[0]({ result: { partial: text } })
  }

  return { engine, recs, fireWake }
}

/** 初始化一个可用的引擎实例。Init an engine ready to start. */
async function readyEngine(warn?: (m: string) => void) {
  const ctx = loadEngine(warn)
  await ctx.engine.init({ modelPath: 'x', keyword: '小逻小逻', sensitivity: 0.5 })
  return ctx
}

describe('唤醒引擎：重启不得丢失唤醒回调', () => {
  /**
   * 本次缺陷的回归用例：播报结束后 `useWakeWord` 以**无参** `start()` 恢复监听，
   * 之后唤醒词必须照常回调。
   *
   * The regression case for this defect: after playback, `useWakeWord` resumes listening with
   * an argument-less `start()`, and the wake word must still invoke the callback afterwards.
   */
  it('以无参重启引擎后，唤醒回调仍然有效', async () => {
    const { engine, fireWake } = await readyEngine()

    const onWake = vi.fn()
    await engine.start(onWake, () => {})

    // 播报期间引擎被停，播报结束后以无参 start() 恢复 —— 正是 useWakeWord.ts 播报结束分支的调用方式。
    engine.stop()
    await engine.start()

    expect(engine.isRunning()).toBe(true)
    fireWake()
    expect(onWake).toHaveBeenCalledTimes(1)
  })

  /** 显式传入新回调时应当替换掉旧的（只有无参启动才保留）。 */
  it('显式传入新回调会替换旧的', async () => {
    const { engine, fireWake } = await readyEngine()

    const first = vi.fn()
    const second = vi.fn()
    await engine.start(first, () => {})
    engine.stop()
    await engine.start(second, () => {})

    fireWake()
    expect(second).toHaveBeenCalledTimes(1)
    expect(first).not.toHaveBeenCalled()
  })

  /** `final` 结果（非 partial）走的也是同一个唤醒出口。 */
  it('final 结果同样触发唤醒回调', async () => {
    const { engine, recs } = await readyEngine()
    const onWake = vi.fn()
    await engine.start(onWake, () => {})
    engine.stop()
    await engine.start()

    recs[recs.length - 1].result[0]({ result: { text: '小逻小逻' } })
    expect(onWake).toHaveBeenCalledTimes(1)
  })

  /** stop() 后再 start() 是播报的两端，引擎必须真的重新跑起来（否则连唤醒都收不到）。 */
  it('stop 后无参 start 能让引擎重新运行', async () => {
    const { engine } = await readyEngine()
    await engine.start(vi.fn(), () => {})
    engine.stop()
    expect(engine.isRunning()).toBe(false)
    await engine.start()
    expect(engine.isRunning()).toBe(true)
  })

  /**
   * 唤醒命中却无人接收时，必须留下可见痕迹 —— 这条路径上的静默失败极难定位
   * （用户只看到「唤不醒」，日志里却什么异常都没有）。
   *
   * A wake hit with nothing listening must leave a visible trace: a silent failure on this
   * path is very hard to diagnose (the user just sees "it won't wake" and the log shows nothing
   * unusual).
   */
  it('唤醒命中但没有回调时打印可见告警', async () => {
    const warns: string[] = []
    const { engine, fireWake } = await readyEngine(m => warns.push(m))
    // 无参启动：从未注册过任何回调，但引擎照常跑起来并识别唤醒词。
    await engine.start()
    fireWake()
    expect(warns.some(w => w.includes('唤醒回调'))).toBe(true)
  })
})
