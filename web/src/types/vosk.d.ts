// Vosk WASM 引擎全局类型声明

interface VoskModel {
  KaldiRecognizer: new (sampleRate: number) => VoskRecognizer
}

interface VoskRecognizer {
  setWords(w: boolean): void
  setPartialWords?(w: boolean): void  // removed from newer vosk-browser, optional
  acceptWaveform(data: Int16Array): boolean
  acceptWaveformFloat?(buffer: Float32Array, sampleRate: number): void
  result(): string
  partialResult(): string
  reset(): void
  free(): void
}

declare const vosk: {
  createModel(path: string | ArrayBuffer | Blob): Promise<VoskModel>
}

// WakeWordEngine — 全局 IIFE (web/lib/wake-word.js)

interface WakeWordConfig {
  modelPath: string
  keyword: string
  sensitivity: number
  /** 已下载的模型字节（tar.gz）；缺省时按 modelPath URL 加载 */
  model?: ArrayBuffer
}

interface WakeStateInfo {
  rms: number
  partial: string
}

declare const WakeWordEngine: {
  init(config: WakeWordConfig): Promise<boolean>
  start(onWake: () => void, onState: (s: WakeStateInfo) => void): Promise<boolean>
  stop(): void
  getStream(): MediaStream | null
  isRunning(): boolean
  isModelLoaded(): boolean
  match(text: string): boolean
}
