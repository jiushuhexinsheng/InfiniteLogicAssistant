/**
 * 音频格式转换工具
 * 浏览器录制 webm → 解码 → 编码为 16kHz mono WAV → base64
 * Audio format conversion utility
 * Browser recorded webm → decode → encode to 16kHz mono WAV → base64
 */

/**
 * 将 Blob（webm/任意浏览器支持的格式）转为 16kHz mono WAV 的 base64
 * Convert Blob (webm/any browser-supported format) to 16kHz mono WAV base64
 * @param blob - 输入音频 Blob / Input audio Blob
 * @returns Promise<string> - base64 编码的 WAV 音频 / base64 encoded WAV audio
 */
export async function blobToWavBase64(blob: Blob): Promise<string> {
  // 将 Blob 转为 ArrayBuffer / Convert Blob to ArrayBuffer
  const arrayBuffer = await blob.arrayBuffer()
  // 创建音频上下文 / Create audio context
  const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()

  // 解码原始音频 / Decode original audio
  const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer)

  // 重采样到 16kHz mono / Resample to 16kHz mono
  const targetRate = 16000
  const offlineCtx = new OfflineAudioContext(1, audioBuffer.duration * targetRate, targetRate)
  const source = offlineCtx.createBufferSource()
  source.buffer = audioBuffer
  source.connect(offlineCtx.destination)
  source.start(0)

  // 渲染重采样后的音频 / Render resampled audio
  const rendered = await offlineCtx.startRendering()
  // 关闭音频上下文释放资源 / Close audio context to release resources
  await audioCtx.close()

  // 编码为 WAV / Encode to WAV
  const wavBytes = encodeWav(rendered, targetRate)
  // 转为 base64 / Convert to base64
  return arrayBufferToBase64(wavBytes)
}

/**
 * 将 AudioBuffer 编码为 WAV 格式
 * Encode AudioBuffer to WAV format
 * @param audioBuffer - 输入音频缓冲区 / Input audio buffer
 * @param sampleRate - 采样率 / Sample rate
 * @returns ArrayBuffer - WAV 格式的 ArrayBuffer / WAV format ArrayBuffer
 */
function encodeWav(audioBuffer: AudioBuffer, sampleRate: number): ArrayBuffer {
  // 单声道 / Mono channel
  const numChannels = 1
  // 16 位采样 / 16-bit samples
  const bitsPerSample = 16
  // 获取第一个通道的音频数据 / Get audio data from first channel
  const data = audioBuffer.getChannelData(0)
  // 计算字节率 / Calculate byte rate
  const byteRate = sampleRate * numChannels * bitsPerSample / 8
  // 计算块对齐 / Calculate block alignment
  const blockAlign = numChannels * bitsPerSample / 8
  // 计算数据大小 / Calculate data size
  const dataSize = data.length * blockAlign
  // 计算缓冲区总大小（44 字节头 + 数据）/ Calculate total buffer size (44-byte header + data)
  const bufferSize = 44 + dataSize

  // 创建 ArrayBuffer / Create ArrayBuffer
  const buf = new ArrayBuffer(bufferSize)
  const view = new DataView(buf)

  // RIFF 头 / RIFF header
  writeString(view, 0, 'RIFF')
  view.setUint32(4, bufferSize - 8, true)
  writeString(view, 8, 'WAVE')

  // fmt 块 / fmt chunk
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)           // 块大小 / chunk size
  view.setUint16(20, 1, true)            // PCM 格式 / PCM format
  view.setUint16(22, numChannels, true)  // 声道数 / number of channels
  view.setUint32(24, sampleRate, true)   // 采样率 / sample rate
  view.setUint32(28, byteRate, true)     // 字节率 / byte rate
  view.setUint16(32, blockAlign, true)   // 块对齐 / block alignment
  view.setUint16(34, bitsPerSample, true) // 位深 / bits per sample

  // data 块 / data chunk
  writeString(view, 36, 'data')
  view.setUint32(40, dataSize, true)     // 数据大小 / data size

  // PCM 采样数据 / PCM sample data
  let offset = 44
  for (let i = 0; i < data.length; i++) {
    // 将浮点采样值限制在 [-1, 1] 范围 / Clamp floating-point sample to [-1, 1]
    const sample = Math.max(-1, Math.min(1, data[i]))
    // 转换为 16 位整数 / Convert to 16-bit integer
    const int16 = sample < 0 ? sample * 32768 : sample * 32767
    // 写入小端序 16 位整数 / Write little-endian 16-bit integer
    view.setInt16(offset, int16, true)
    offset += 2
  }

  return buf
}

/**
 * 将字符串写入 DataView
 * Write string to DataView
 * @param view - DataView 对象 / DataView object
 * @param offset - 起始偏移量 / Start offset
 * @param str - 要写入的字符串 / String to write
 */
function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    // 写入字符的 ASCII 码 / Write ASCII code of character
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}

/**
 * 将 ArrayBuffer 转为 base64 字符串
 * Convert ArrayBuffer to base64 string
 * @param buffer - 输入 ArrayBuffer / Input ArrayBuffer
 * @returns string - base64 编码字符串 / base64 encoded string
 */
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  // 创建字节数组 / Create byte array
  const bytes = new Uint8Array(buffer)
  let binary = ''
  // 将每个字节转为字符 / Convert each byte to character
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  // 编码为 base64 / Encode to base64
  return btoa(binary)
}
