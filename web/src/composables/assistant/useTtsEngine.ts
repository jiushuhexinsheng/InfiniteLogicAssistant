import { computed } from 'vue'
import { ttsSettings, saveTts } from './useTts'
import type { TtsEngine } from './useTts'
import { useConfig } from '../useApi'

/**
 * 语音引擎选择的单一来源（两卡堆叠布局的卡1 与卡2 共用）。
 *
 * engine 是纯用户意图（localStorage），不因后端不可用而回退展示 ——
 * 否则「后端未配置 → 无法选 API → 永远到不了 API 配置卡」会形成死循环；
 * 播报失败时 speakApi 已有自动回退本地的兜底。
 *
 * Single source of truth for the TTS engine choice (shared by both stacked
 * cards). `engine` is pure user intent persisted to localStorage and is NOT
 * forced back to browser when the backend is unavailable — otherwise "backend
 * unconfigured → cannot pick API → never reach the API config card" would be a
 * dead loop; speakApi already auto-falls back to the browser engine at runtime.
 *
 * @returns 当前引擎、后端可用性、切换函数。Current engine, backend availability, switch fn.
 */
export function useTtsEngine() {
  const app = useConfig()

  /** 后端 TTS 可用（/api/config 的 tts_available）。Backend TTS available. */
  const apiAvailable = computed(() => app.config.value?.tts_available === true)

  /** 用户选择的引擎。The user-selected engine. */
  const engine = computed<TtsEngine>(() => ttsSettings.value.engine)

  /**
   * 切换引擎并立即持久化。
   * Switch the engine and persist immediately.
   *
   * @param e 目标引擎。Target engine.
   */
  function setEngine(e: TtsEngine) {
    ttsSettings.value.engine = e
    saveTts()
  }

  return { engine, apiAvailable, setEngine }
}
