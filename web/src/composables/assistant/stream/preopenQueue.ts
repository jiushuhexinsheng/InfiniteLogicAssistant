/**
 * 预 OPEN 音频帧的环形缓冲：WS 尚未连通/尚未发出 start 时先缓存，连通后按序补发。
 *
 * Ring buffer for audio frames produced before the WebSocket is OPEN (or before the
 * `start` JSON went out): buffer them and flush in order once connected.
 *
 * 上限 100 帧（20ms/帧 = 2s）：超出丢最旧的一帧，保证内存有界，同时尽量保住最近的人声。
 * Cap = 100 frames (20 ms each = 2 s): on overflow the oldest frame is dropped, keeping
 * memory bounded while favouring the most recent speech.
 */
export interface PreopenQueue {
  /** 入队一帧；超出上限时丢最旧。Push a frame; drop the oldest on overflow. */
  push(frame: ArrayBuffer): void
  /** 取出全部帧并清空（保持入队顺序）。Drain all frames in FIFO order and clear. */
  drain(): ArrayBuffer[]
  /** 清空。Clear. */
  clear(): void
  /** 当前帧数。Current frame count. */
  readonly size: number
  /** 容量上限（帧）。Capacity in frames. */
  readonly capacity: number
}

/** 默认上限：100 帧 × 20ms = 2s。Default cap: 100 frames × 20 ms = 2 s. */
export const PREOPEN_MAX_FRAMES = 100

/**
 * 创建预 OPEN 帧队列。Create a pre-open frame queue.
 *
 * @param maxFrames - 容量上限（帧，≥1）。Capacity in frames (≥1).
 * @returns 队列句柄。The queue handle.
 */
export function createPreopenQueue(maxFrames: number = PREOPEN_MAX_FRAMES): PreopenQueue {
  const capacity = Math.max(1, Math.floor(maxFrames))
  const frames: ArrayBuffer[] = []

  return {
    push(frame: ArrayBuffer) {
      frames.push(frame)
      if (frames.length > capacity) frames.shift()
    },
    drain(): ArrayBuffer[] {
      const out = frames.slice()
      frames.length = 0
      return out
    },
    clear() {
      frames.length = 0
    },
    get size() {
      return frames.length
    },
    get capacity() {
      return capacity
    },
  }
}
