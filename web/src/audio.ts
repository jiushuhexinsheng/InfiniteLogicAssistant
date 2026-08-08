/**
 * 音频格式转换工具
 * 浏览器录制 webm → 解码 → 编码为 16kHz mono WAV → base64
 */

/**
 * 将 Blob（webm/任意浏览器支持的格式）转为 16kHz mono WAV 的 base64
 */
export async function blobToWavBase64(blob: Blob): Promise<string> {
  const arrayBuffer = await blob.arrayBuffer()
  const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()

  // 解码原始音频
  const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer)

  // 重采样到 16kHz mono
  const targetRate = 16000
  const offlineCtx = new OfflineAudioContext(1, audioBuffer.duration * targetRate, targetRate)
  const source = offlineCtx.createBufferSource()
  source.buffer = audioBuffer
  source.connect(offlineCtx.destination)
  source.start(0)

  const rendered = await offlineCtx.startRendering()
  await audioCtx.close()

  // 编码为 WAV
  const wavBytes = encodeWav(rendered, targetRate)
  return arrayBufferToBase64(wavBytes)
}

/** 将 AudioBuffer 编码为 WAV 格式 */
function encodeWav(audioBuffer: AudioBuffer, sampleRate: number): ArrayBuffer {
  const numChannels = 1
  const bitsPerSample = 16
  const data = audioBuffer.getChannelData(0)
  const byteRate = sampleRate * numChannels * bitsPerSample / 8
  const blockAlign = numChannels * bitsPerSample / 8
  const dataSize = data.length * blockAlign
  const bufferSize = 44 + dataSize

  const buf = new ArrayBuffer(bufferSize)
  const view = new DataView(buf)

  // RIFF header
  writeString(view, 0, 'RIFF')
  view.setUint32(4, bufferSize - 8, true)
  writeString(view, 8, 'WAVE')

  // fmt chunk
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)           // chunk size
  view.setUint16(20, 1, true)            // PCM
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, byteRate, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, bitsPerSample, true)

  // data chunk
  writeString(view, 36, 'data')
  view.setUint32(40, dataSize, true)

  // PCM samples
  let offset = 44
  for (let i = 0; i < data.length; i++) {
    const sample = Math.max(-1, Math.min(1, data[i]))
    const int16 = sample < 0 ? sample * 32768 : sample * 32767
    view.setInt16(offset, int16, true)
    offset += 2
  }

  return buf
}

function writeString(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}
