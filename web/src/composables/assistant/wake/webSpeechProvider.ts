/**
 * Web Speech API 唤醒提供者。
 *
 * 使用浏览器内置的 Web Speech API 进行本地语音识别，零延迟、不上传音频。
 * 识别结果通过回调返回，由 orchestrator 层调用 `detectWake` 进行唤醒词匹配。
 *
 * 注意：Web Speech API 不接受 blob 输入，而是自己管理麦克风流。
 * 因此本提供者的 `detect()` 方法不会被回退链调用；orchestrator 通过 `start(onResult)` 获取识别文本，
 * 再自行调用 `detectWake` 匹配。
 *
 * Web Speech API wake provider.
 * Uses the browser's built-in Web Speech API for local speech recognition — zero latency, no upload.
 * Results are returned via callback; the orchestrator calls `detectWake` for matching.
 *
 * Note: Web Speech API does not accept blob input — it manages its own mic stream.
 * This provider's `detect()` is never called by the fallback chain; the orchestrator obtains
 * recognition text via `start(onResult)` and matches with `detectWake` itself.
 */

import { detectWake } from '../wakeMatch'
import type { WebSpeechWakeProvider } from './types'

/**
 * 创建 Web Speech API 唤醒提供者。
 *
 * Create a Web Speech API wake provider.
 */
export function createWebSpeechProvider(): WebSpeechWakeProvider {
  /** Web Speech API 识别实例。The Web Speech API recognition instance. */
  let recognition: any = null
  /** 本地识别是否在运行。Whether local recognition is running. */
  let active = false
  /** 结果回调（isFinal=false 为中间结果，true 为最终结果）。Result callback. */
  let resultCallback: ((text: string, isFinal: boolean) => void) | null = null

  return {
    name: 'web-speech',

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    async detect(_blob: Blob, _keywords: string[]) {
      // Web Speech API 不走 blob 路径；orchestrator 通过 start(onResult) 获取结果。
      // Web Speech API does not use the blob path; the orchestrator gets results via start(onResult).
      return { matched: false, command: '' }
    },

    isAvailable(): boolean {
      if (typeof window === 'undefined') return false
      return !!(window as any).SpeechRecognition || !!(window as any).webkitSpeechRecognition
    },

    start(onResult: (text: string, isFinal: boolean) => void): boolean {
      if (typeof window === 'undefined') return false
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (!SR) return false

      try {
        recognition = new SR()
        recognition.continuous = true
        recognition.interimResults = true
        recognition.lang = 'zh-CN'
        recognition.maxAlternatives = 1
        resultCallback = onResult

        recognition.onresult = (event: any) => {
          const result = event.results[event.results.length - 1]
          const transcript = result[0].transcript
          // 中间结果和最终结果都回调，由调用方按 isFinal 分别处理
          // Both interim and final results callback; the caller handles them by isFinal
          resultCallback?.(transcript, result.isFinal)
        }

        recognition.onerror = (e: any) => {
          if (e.error === 'no-speech' || e.error === 'aborted') return
          console.warn('[wake:web-speech] 识别错误:', e.error)
        }

        recognition.onend = () => {
          // Chrome 会自动停止识别；若仍在监听则重启
          // Chrome auto-stops recognition; restart if still active
          if (active) {
            setTimeout(() => {
              if (active) {
                try { recognition.start() } catch { /* ignore */ }
              }
            }, 100)
          }
        }

        recognition.start()
        active = true
        return true
      } catch (e) {
        console.warn('[wake:web-speech] 启动失败:', e)
        recognition = null
        active = false
        return false
      }
    },

    stop(): void {
      active = false
      resultCallback = null
      if (recognition) {
        try { recognition.stop() } catch { /* ignore */ }
        recognition = null
      }
    },

    isRunning(): boolean {
      return active
    },

    dispose(): void {
      this.stop()
    },
  }
}

/**
 * 处理本地识别结果：匹配唤醒词并返回结果。
 *
 * 这是一个纯函数，供 orchestrator 在收到 Web Speech API 的识别文本后调用。
 *
 * Handle a local recognition result: match the wake word and return the result.
 * A pure function for the orchestrator to call after receiving Web Speech API text.
 *
 * @param text 识别出的文本。The recognized text.
 * @param keywords 已配置的唤醒词列表。The configured wake words.
 * @returns 匹配结果（含 matched + command）。The match result.
 */
export function matchLocalWake(text: string, keywords: string[]): { matched: boolean; command: string } {
  const trimmed = text.trim()
  if (!trimmed) return { matched: false, command: '' }
  return detectWake(trimmed, keywords)
}