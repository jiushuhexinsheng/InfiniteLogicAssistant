/**
 * 唤醒回退链协调器。
 *
 * 按当前唤醒模式选择 provider 列表，依次尝试检测，第一个 matched 胜出。
 * 不可用的 provider 会被跳过（`isAvailable()` 返回 false）。
 *
 * Wake fallback-chain coordinator.
 * Selects a provider list by the current wake mode, tries each in order, and the first
 * `matched` wins. Unavailable providers (`isAvailable()` returns false) are skipped.
 */

import type { WakeMode } from '../store'
import type { WakeProvider, WakeResult, WebSpeechWakeProvider } from './types'
import { createCloudAsrProvider, type CloudAsrApi } from './cloudAsrProvider'
import { createWebSpeechProvider } from './webSpeechProvider'
import { createSherpaKwsProvider } from './sherpaKwsProvider'

/** 模块级 provider 单例（延迟创建，首次使用时初始化）。Module-level provider singletons (lazy-created). */
let sherpaProvider: WakeProvider | null = null
let cloudProvider: WakeProvider | null = null
let webSpeechProvider: WebSpeechWakeProvider | null = null

/** 获取或创建 Sherpa-ONNX KWS 提供者。Get or create the Sherpa-ONNX KWS provider. */
function getSherpa(): WakeProvider {
  if (!sherpaProvider) sherpaProvider = createSherpaKwsProvider()
  return sherpaProvider
}

/** 获取或创建云端 ASR 提供者（api 由首次调用时注入，后续忽略）。
 *  mode 变化时重建 —— cloud 模式随请求下发以旁路后端 KWS 闸门，缓存旧 mode 会失效。
 *  Get or create the cloud ASR provider. Recreated when the mode changes: the mode
 *  travels with the request so cloud can bypass the backend KWS gate, and caching a
 *  stale mode would break that. */
let cloudMode = ''
function getCloud(api?: CloudAsrApi, mode: string = 'auto'): WakeProvider {
  if ((!cloudProvider || mode !== cloudMode) && api) {
    cloudProvider = createCloudAsrProvider(api, mode)
    cloudMode = mode
  }
  return cloudProvider!
}

/** 获取或创建 Web Speech API 提供者。Get or create the Web Speech API provider. */
function getWebSpeech(): WebSpeechWakeProvider {
  if (!webSpeechProvider) webSpeechProvider = createWebSpeechProvider()
  return webSpeechProvider
}

/**
 * 按唤醒模式返回 provider 链（已过滤不可用的）。
 *
 * 注意：Web Speech API 提供者在 auto 链中也被包含，但它不走 `detect(blob)` 路径，
 * orchestrator 需要特殊处理（通过 `start(onResult)` 获取文本）。
 * 这里把它放在链中是为了让 `getChain` 能返回完整的 provider 列表，
 * 但 `detectInChain` 会跳过它（因为它总是返回 `{ matched: false }`）。
 *
 * Returns the provider chain for the given wake mode (unavailable ones filtered out).
 * Note: the Web Speech API provider is included in the `auto` chain but does not use the
 * `detect(blob)` path — the orchestrator handles it specially via `start(onResult)`.
 * It is in the chain so `getChain` returns a complete list, but `detectInChain` skips it
 * (it always returns `{ matched: false }`).
 *
 * @param mode 唤醒模式。The wake mode.
 * @param api 云端 API 客户端（注入给 cloud provider）。The cloud API client (injected into the cloud provider).
 * @returns provider 列表（按优先级排序）。The provider list (sorted by priority).
 */
export function getChain(mode: WakeMode, api?: CloudAsrApi): WakeProvider[] {
  switch (mode) {
    case 'local':
      // 本地判定 = 后端 KWS 闸门（同端点）：KWS 未命中不上云，命中才调 ASR 抬指令。
      // 浏览器 WASM KWS（sherpaKwsProvider 占位）留给后续完全离线场景。
      // Local judging = the backend KWS gate (same endpoint): misses never reach the
      // cloud, hits call ASR for command extraction. The browser-WASM sherpa provider
      // (placeholder) stays reserved for a fully-offline future.
      return [getCloud(api, 'local')]
    case 'cloud':
      return [getCloud(api, 'cloud')]
    case 'webspeech':
      // Web Speech API 不走 detect(blob) 路径，返回空链；orchestrator 特殊处理。
      // Web Speech API does not use the detect(blob) path; orchestrator handles it specially.
      return []
    case 'auto':
    default: {
      const chain: WakeProvider[] = []
      const sherpa = getSherpa()
      const cloud = getCloud(api, 'auto')
      // Sherpa-ONNX 优先（本地、零延迟）
      // Sherpa-ONNX first (local, zero latency)
      if (sherpa.isAvailable()) chain.push(sherpa)
      // 云端 ASR 其次（准确但有延迟）
      // Cloud ASR next (accurate but with latency)
      if (cloud.isAvailable()) chain.push(cloud)
      // Web Speech API 不加入链（orchestrator 特殊处理）
      // Web Speech API not in chain (orchestrator handles specially)
      return chain
    }
  }
}

/**
 * 在 provider 链中依次尝试检测，第一个 matched 胜出。
 *
 * Try detection across the provider chain; the first `matched` wins.
 *
 * @param chain provider 链。The provider chain.
 * @param blob 一段音频。One audio segment.
 * @param keywords 已配置的唤醒词。The configured wake words.
 * @returns 匹配结果；全不匹配返回 `{ matched: false, command: '' }`。
 *          The match result; `{ matched: false, command: '' }` if none matched.
 */
export async function detectInChain(
  chain: WakeProvider[],
  blob: Blob,
  keywords: string[],
): Promise<WakeResult> {
  let lastError: Error | null = null
  for (const provider of chain) {
    if (!provider.isAvailable()) continue
    try {
      const result = await provider.detect(blob, keywords)
      if (result.matched) return result
    } catch (e) {
      // 单个 provider 失败不中断回退链，继续尝试下一个
      // A single provider failure does not break the chain; continue to the next
      lastError = e as Error
    }
  }
  // 全部 provider 都失败才抛出（触发熔断）；有成功的但未匹配则返回 matched: false
  // Only throw when ALL providers failed (trips the breaker); a successful-but-unmatched result returns matched: false
  if (lastError) throw lastError
  return { matched: false, command: '' }
}

/**
 * 获取 Web Speech API 提供者（供 orchestrator 特殊处理）。
 *
 * Get the Web Speech API provider (for orchestrator special handling).
 *
 * @returns Web Speech API 提供者实例。The Web Speech API provider instance.
 */
export function getWebSpeechProvider(): WebSpeechWakeProvider {
  return getWebSpeech()
}

/**
 * 窥探 Web Speech API 提供者（不创建实例）。
 *
 * 供 stopListening 等「只在已创建时才需要操作」的场景使用，避免不必要地分配对象。
 *
 * Peek at the Web Speech API provider (without creating it).
 * For callers like stopListening that only need to act when the instance already exists.
 *
 * @returns 已创建的实例，未创建时为 null。The existing instance, or null if never created.
 */
export function peekWebSpeechProvider(): WebSpeechWakeProvider | null {
  return webSpeechProvider
}

/**
 * 释放所有 provider 资源。
 *
 * Dispose all provider resources.
 */
export function disposeAll(): void {
  sherpaProvider?.dispose?.()
  cloudProvider?.dispose?.()
  webSpeechProvider?.dispose?.()
  sherpaProvider = null
  cloudProvider = null
  webSpeechProvider = null
}