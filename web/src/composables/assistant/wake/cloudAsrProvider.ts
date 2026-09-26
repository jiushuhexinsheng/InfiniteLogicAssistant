/**
 * 云端 ASR 唤醒提供者。
 *
 * 将 VAD 分段的音频上传到后端 `/api/voice/wake`，由后端完成 ASR 转写与唤醒词判定。
 * 优点：识别准确率高（使用配置的云端 ASR 服务）；缺点：有延迟、消耗 API 额度、音频离开本机。
 *
 * `api` 由调用方注入（而非直接导入），与 orchestrator 的依赖注入模式一致 —— 测试只需
 * mock 一个导入路径。
 *
 * Cloud ASR wake provider.
 * Uploads VAD-segmented audio to the backend `/api/voice/wake` endpoint, which performs ASR
 * transcription and wake-word judgement. Pros: high accuracy (uses the configured cloud ASR);
 * Cons: latency, API quota consumption, audio leaves the device.
 *
 * `api` is injected by the caller (not directly imported), consistent with the orchestrator's
 * dependency-injection pattern — tests only need to mock one import path.
 */

import type { WakeProvider, WakeResult } from './types'

/** 云端 API 接口（只用到 wakeDetect）。Cloud API interface (only wakeDetect is used). */
export interface CloudAsrApi {
  wakeDetect(blob: Blob, opts?: { mode?: string }): Promise<{ ok?: boolean; matched?: boolean; command?: string; text?: string; error?: string }>
}

/**
 * 创建云端 ASR 唤醒提供者。
 *
 * mode 随请求下发：cloud 显式旁路后端 KWS 闸门（纯云端判定，最大召回）。
 *
 * Create a cloud ASR wake provider. The mode travels with the request: cloud
 * explicitly bypasses the backend KWS gate (pure cloud judging, maximum recall).
 *
 * @param api 云端 API 客户端（由调用方注入）。The cloud API client (injected by the caller).
 * @param mode 唤醒模式（随请求下发）。Wake mode (travels with the request).
 */
export function createCloudAsrProvider(api: CloudAsrApi, mode: string = 'auto'): WakeProvider {
  return {
    name: 'cloud-asr',

    async detect(blob: Blob, _keywords: string[]): Promise<WakeResult> {
      // 不捕获异常：让调用方（orchestrator）处理失败并触发熔断。
      // ok: false 也视为失败并抛出，使 orchestrator 的 onUploadFailed 能正确计数。
      // Do NOT catch exceptions: let the caller (orchestrator) handle failures and trip the breaker.
      // `ok: false` is also treated as a failure and thrown, so the orchestrator's onUploadFailed
      // can count it correctly.
      const r = await api.wakeDetect(blob, { mode })
      if (!r?.ok) throw new Error(r?.error || 'wakeDetect failed')
      return { matched: !!r.matched, command: r.command || '' }
    },

    isAvailable(): boolean {
      // 云端 ASR 始终可用（只要后端在跑）
      // Cloud ASR is always available (as long as the backend is running)
      return true
    },
  }
}