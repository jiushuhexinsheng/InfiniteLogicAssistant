/**
 * Sherpa-ONNX KWS 唤醒提供者（占位实现）。
 *
 * Sherpa-ONNX 是专为关键词检测（KWS）设计的轻量级引擎，模型仅 ~3.3MB，
 * 基于 zipformer-wenetspeech 训练，中文原生支持，精度远优于通用 ASR。
 *
 * 当前为占位实现：`isAvailable()` 返回 false。
 *
 * **Go/No-Go 评估（2026-09-29，docs/designs/03-B 批1）：No-Go**，接入暂缓：
 * - npm 官方包 `sherpa-onnx@1.13.8` 只附带 **NodeJS 版 wasm**（README 明示 Node ≥ 18，
 *   包内仅 `sherpa-onnx-wasm-nodejs.wasm`，无浏览器构建）；
 * - GitHub release 的 wasm 资产只有 TTS/VAD/语音增强，**没有 KWS 浏览器包**；
 * - 可行路径只剩两条重活：emscripten 自编 sherpa-onnx fork，或 onnxruntime-web 手搬
 *   zipformer KWS 双模型状态机 —— 持续维护成本高，而增量收益仅「提示音提前 ~1.5s +
 *   少一次本机 localhost 快检往返」（判定本地化、零云成本已由后端 KWS 闸门保证）。
 * 结论：占位保留，等官方出浏览器 KWS 构建或社区包装再启用。
 *
 * Sherpa-ONNX KWS wake provider (placeholder).
 * Sherpa-ONNX is a lightweight keyword-spotting engine (~3.3MB model), trained on wenetspeech,
 * with native Chinese support and far better accuracy than general-purpose ASR.
 * Currently a placeholder: `isAvailable()` returns false.
 *
 * **Go/No-Go evaluation (2026-09-29, docs/designs/03-B batch 1): No-Go**, integration
 * deferred: the official npm package ships only a **NodeJS wasm** (README: Node ≥ 18;
 * package holds `sherpa-onnx-wasm-nodejs.wasm`, no browser build); GitHub release wasm
 * assets cover TTS/VAD/speech-enhancement only — **no browser KWS bundle**; the remaining
 * paths (emscripten-building a sherpa fork, or hand-porting the zipformer KWS two-model
 * state machine onto onnxruntime-web) are heavy ongoing maintenance for gains limited to
 * ~1.5s earlier chime plus one fewer localhost quick-check round-trip (local-only,
 * zero-cloud judgement is already guaranteed by the backend KWS gate). Verdict: keep the
 * placeholder until an official browser KWS build or community wrapper exists.
 *
 * @see https://github.com/k2-fsa/sherpa-onnx
 * @see docs/designs/03-voice-conversation.md — B 节 Go/No-Go 评估
 * @see docs/superpowers/specs/2026-09-13-wake-detection-rework-design.md — 子项目 2
 */

import type { WakeProvider, WakeResult } from './types'

/**
 * 创建 Sherpa-ONNX KWS 唤醒提供者（占位；Go/No-Go = No-Go，见文件头）。
 *
 * Create a Sherpa-ONNX KWS wake provider (placeholder; Go/No-Go = No-Go, see header).
 *
 * 将来启用的接入步骤（待官方浏览器构建就绪）：
 * 1. 接入浏览器版 sherpa-onnx WASM（官方或社区包装）
 * 2. 模型复用 models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01/（经 /models/kws 路由）
 * 3. 在 Web Worker 中初始化 spotter，AudioWorklet 喂 16kHz 帧（流式提前命中）
 * 4. 实现 `detect()` — 段窗内命中缓存查询；`isAvailable()` = worker + 模型就绪
 *
 * Future integration steps (once an official browser build exists):
 * 1. Wire the browser sherpa-onnx WASM (official or community wrapper)
 * 2. Reuse the model under models/sherpa-onnx-kws-... (served via /models/kws)
 * 3. Init the spotter in a Web Worker, feed 16kHz frames from an AudioWorklet (streaming early hit)
 * 4. Implement `detect()` — query the per-segment hit cache; `isAvailable()` = worker + model ready
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