/**
 * Vosk WASM 引擎全局类型声明
 * Global type declarations for Vosk WASM engine
 */

/**
 * Vosk 语音识别模型接口
 * Interface for Vosk speech recognition model
 */
interface VoskModel {
  /** 创建 Kaldi 识别器实例 / Create a Kaldi recognizer instance */
  KaldiRecognizer: new (sampleRate: number) => VoskRecognizer
}

/**
 * Vosk 语音识别器接口
 * Interface for Vosk speech recognizer
 */
interface VoskRecognizer {
  /** 设置是否返回单词信息 / Set whether to return word information */
  setWords(w: boolean): void
  /** 设置是否返回部分单词信息（新版本已移除，可选） / Set whether to return partial word information (removed from newer vosk-browser, optional) */
  setPartialWords?(w: boolean): void
  /** 接受波形数据进行识别 / Accept waveform data for recognition */
  acceptWaveform(data: Int16Array): boolean
  /** 接受浮点波形数据进行识别 / Accept float waveform data for recognition */
  acceptWaveformFloat?(buffer: Float32Array, sampleRate: number): void
  /** 获取识别结果 / Get recognition result */
  result(): string
  /** 获取部分识别结果 / Get partial recognition result */
  partialResult(): string
  /** 重置识别器状态 / Reset recognizer state */
  reset(): void
  /** 释放识别器资源 / Free recognizer resources */
  free(): void
}

/**
 * Vosk 全局对象，用于创建语音识别模型
 * Global Vosk object for creating speech recognition models
 */
declare const vosk: {
  /** 创建 Vosk 模型实例 / Create a Vosk model instance */
  createModel(path: string): Promise<VoskModel>
}

/**
 * WakeWordEngine — 全局 IIFE (web/lib/wake-word.js)
 * WakeWordEngine — Global IIFE (web/lib/wake-word.js)
 */

/**
 * 唤醒词配置接口
 * Interface for wake word configuration
 */
interface WakeWordConfig {
  /** 模型路径 / Model path */
  modelPath: string
  /** 唤醒词关键词 / Wake word keyword */
  keyword: string
  /** 灵敏度 / Sensitivity */
  sensitivity: number
}

/**
 * 唤醒状态信息接口
 * Interface for wake state information
 */
interface WakeStateInfo {
  /** 均方根值 / Root mean square value */
  rms: number
  /** 部分识别文本 / Partial recognition text */
  partial: string
}

/**
 * 唤醒词引擎全局对象
 * Global wake word engine object
 */
declare const WakeWordEngine: {
  /** 初始化唤醒词引擎 / Initialize wake word engine */
  init(config: WakeWordConfig): Promise<boolean>
  /** 启动唤醒词检测 / Start wake word detection */
  start(onWake: () => void, onState: (s: WakeStateInfo) => void): Promise<boolean>
  /** 停止唤醒词检测 / Stop wake word detection */
  stop(): void
  /** 获取音频流 / Get audio stream */
  getStream(): MediaStream | null
  /** 检查是否正在运行 / Check if running */
  isRunning(): boolean
  /** 检查模型是否已加载 / Check if model is loaded */
  isModelLoaded(): boolean
  /** 匹配文本是否为唤醒词 / Check if text matches wake word */
  match(text: string): boolean
}
