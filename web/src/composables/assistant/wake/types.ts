/**
 * 唤醒子系统共享类型定义。
 *
 * 每个唤醒检测提供者（Sherpa-ONNX KWS、云端 ASR、Web Speech API）都实现 `WakeProvider` 接口；
 * 回退链协调器按模式选择 provider 列表，依次尝试，第一个 matched 胜出。
 *
 * Shared type definitions for the wake subsystem.
 * Every wake-detection provider (Sherpa-ONNX KWS, Cloud ASR, Web Speech API) implements the
 * `WakeProvider` interface; the fallback-chain coordinator picks a provider list by mode and
 * tries them in order — the first `matched` wins.
 */

/** 唤醒检测结果。Wake detection result. */
export interface WakeResult {
  /** 是否命中唤醒词。Whether the wake word was detected. */
  matched: boolean
  /** 唤醒词之后的指令（仅唤醒词时为空串）。Command after the wake word (empty for bare wake). */
  command: string
}

/**
 * 唤醒检测提供者接口。
 *
 * 每个 provider 封装一种唤醒检测方案，对外暴露统一的 `detect` 方法。
 * 调用方无需关心底层是本地 WASM、云端 HTTP 还是浏览器原生 API。
 *
 * Wake-detection provider interface.
 * Each provider encapsulates one detection backend and exposes a uniform `detect` method.
 * Callers need not know whether the engine is local WASM, a cloud HTTP call, or a browser API.
 */
export interface WakeProvider {
  /** 提供者名称（用于日志和调试）。Provider name (for logging and debugging). */
  readonly name: string

  /**
   * 检测一段音频是否包含唤醒词。
   *
   * 由 VAD 分段录音器产出的音频 blob，经由本方法判定是否命中唤醒词。
   * 某些提供者（如 Web Speech API）不走这条路径，而是在内部自行管理音频流；
   * 此时本方法不会被调用，orchestrator 会通过其他方式获取结果。
   *
   * Detect whether an audio segment contains a wake word.
   * The blob comes from the VAD segment recorder. Some providers (e.g. Web Speech API)
   * manage their own audio stream internally and never have `detect` called — the
   * orchestrator obtains their results through a separate callback path.
   *
   * @param blob 一段音频。One audio segment.
   * @param keywords 已配置的唤醒词列表。The configured wake words.
   * @returns 检测结果。The detection result.
   */
  detect(blob: Blob, keywords: string[]): Promise<WakeResult>

  /**
   * 引擎是否可用（能力探测结果）。
   *
   * 启动时调用一次，结果应被缓存。返回 false 的 provider 会被回退链跳过。
   *
   * Whether the engine is available (capability probe result).
   * Called once at startup; the result should be cached. Providers returning false are
   * skipped by the fallback chain.
   */
  isAvailable(): boolean

  /**
   * 初始化引擎（首次使用前调用）。
   *
   * 对于需要加载 WASM 或建立连接的 provider，在第一次 detect 前调用。
   * 返回 true 表示初始化成功，false 表示不可用。
   *
   * Initialize the engine (called before first use).
   * For providers that need to load WASM or establish a connection.
   * Returns true on success, false if unavailable.
   */
  init?(): Promise<boolean>

  /**
   * 释放资源。
   *
   * 停止监听、关闭连接、释放 WASM 内存等。
   *
   * Release resources.
   * Stop listening, close connections, free WASM memory, etc.
   */
  dispose?(): void
}

/**
 * Web Speech API 提供者的特殊接口。
 *
 * Web Speech API 不接受 blob 输入，而是自己管理麦克风流并持续输出识别结果。
 * 这个接口扩展了标准 WakeProvider，增加了流式控制和结果回调。
 *
 * Special interface for the Web Speech API provider.
 * Web Speech API does not accept blob input; it manages its own mic stream and continuously
 * outputs recognition results. This interface extends the standard WakeProvider with
 * stream control and result callbacks.
 */
export interface WebSpeechWakeProvider extends WakeProvider {
  /** 启动本地识别。Start local recognition.
   *  `isFinal` 为 false 时是中间结果（供 partialText 显示），为 true 时是最终结果。
   *  `isFinal: false` means an interim result (for partialText display); `true` means final. */
  start(onResult: (text: string, isFinal: boolean) => void): boolean
  /** 停止本地识别。Stop local recognition. */
  stop(): void
  /** 本地识别是否正在运行。Whether local recognition is running. */
  isRunning(): boolean
}