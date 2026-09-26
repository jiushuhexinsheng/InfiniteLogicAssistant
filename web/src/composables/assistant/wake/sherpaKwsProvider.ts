/**
 * Sherpa-ONNX KWS 唤醒提供者（占位实现）。
 *
 * Sherpa-ONNX 是专为关键词检测（KWS）设计的轻量级引擎，模型仅 ~3.3MB，
 * 基于 zipformer-wenetspeech 训练，中文原生支持，精度远优于通用 ASR。
 *
 * 当前为占位实现：`isAvailable()` 返回 false，后续接入 sherpa-onnx-web WASM 后启用。
 *
 * Sherpa-ONNX KWS wake provider (placeholder).
 * Sherpa-ONNX is a lightweight keyword-spotting engine (~3.3MB model), trained on wenetspeech,
 * with native Chinese support and far better accuracy than general-purpose ASR.
 * Currently a placeholder: `isAvailable()` returns false. Will be enabled after integrating
 * sherpa-onnx-web WASM.
 *
 * @see https://github.com/k2-fsa/sherpa-onnx
 * @see docs/superpowers/specs/2026-09-13-wake-detection-rework-design.md — 子项目 2
 */

import type { WakeProvider, WakeResult } from './types'

/**
 * 创建 Sherpa-ONNX KWS 唤醒提供者（占位）。
 *
 * Create a Sherpa-ONNX KWS wake provider (placeholder).
 *
 * 后续接入步骤：
 * 1. 安装 `sherpa-onnx-web` npm 包
 * 2. 下载 KWS 模型（sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01）
 * 3. 在 Web Worker 中初始化 sherpa-onnx WASM
 * 4. 实现 `detect()` — 音频 blob → PCM → keyword spotter → 结果
 * 5. `isAvailable()` 检查 WASM 是否加载成功
 *
 * Integration steps:
 * 1. Install `sherpa-onnx-web` npm package
 * 2. Download KWS model (sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01)
 * 3. Initialize sherpa-onnx WASM in a Web Worker
 * 4. Implement `detect()` — audio blob → PCM → keyword spotter → result
 * 5. `isAvailable()` checks whether WASM loaded successfully
 */
export function createSherpaKwsProvider(): WakeProvider {
  /** WASM 是否已加载成功。Whether WASM loaded successfully. */
  let wasmReady = false
  /** 初始化是否已尝试过。Whether init has been attempted. */
  let initAttempted = false

  return {
    name: 'sherpa-kws',

    async detect(_blob: Blob, _keywords: string[]): Promise<WakeResult> {
      if (!wasmReady) return { matched: false, command: '' }

      // TODO: 接入 sherpa-onnx-web WASM
      // 1. 将 blob 转为 PCM (16kHz mono float32)
      // 2. fed PCM 到 keyword spotter
      // 3. 检查是否有匹配的关键词
      // Integrate sherpa-onnx-web WASM:
      // 1. Convert blob to PCM (16kHz mono float32)
      // 2. Feed PCM to keyword spotter
      // 3. Check for keyword matches
      return { matched: false, command: '' }
    },

    isAvailable(): boolean {
      return wasmReady
    },

    async init(): Promise<boolean> {
      if (initAttempted) return wasmReady
      initAttempted = true

      // TODO: 加载 sherpa-onnx-web WASM
      // 1. 检查浏览器是否支持 WASM
      // 2. 加载 sherpa-onnx WASM 模块
      // 3. 下载并初始化 KWS 模型
      // 4. 创建 keyword spotter 实例
      // Load sherpa-onnx-web WASM:
      // 1. Check browser WASM support
      // 2. Load sherpa-onnx WASM module
      // 3. Download and initialize KWS model
      // 4. Create keyword spotter instance

      console.info('[wake:sherpa-kws] Sherpa-ONNX KWS 尚未接入，当前为占位实现')
      wasmReady = false
      return false
    },

    dispose(): void {
      wasmReady = false
      initAttempted = false
      // TODO: 释放 sherpa-onnx WASM 资源
    },
  }
}