import { describe, expect, it } from 'vitest'
import { createPreopenQueue, PREOPEN_MAX_FRAMES } from '../stream/preopenQueue'

/** 造一个可辨识的帧。Make an identifiable frame. */
function frame(n: number): ArrayBuffer {
  return new Int16Array([n]).buffer
}

describe('createPreopenQueue', () => {
  it('按 FIFO 顺序 drain 并清空', () => {
    const q = createPreopenQueue()
    q.push(frame(1))
    q.push(frame(2))
    q.push(frame(3))
    expect(q.size).toBe(3)

    expect(q.drain().map((b) => new Int16Array(b)[0])).toEqual([1, 2, 3])
    expect(q.size).toBe(0)
    expect(q.drain()).toEqual([])
  })

  it('超出上限时丢最旧的一帧', () => {
    const q = createPreopenQueue(3)
    for (const n of [1, 2, 3, 4, 5]) q.push(frame(n))
    expect(q.size).toBe(3)
    expect(q.drain().map((b) => new Int16Array(b)[0])).toEqual([3, 4, 5])
  })

  it('默认上限是 100 帧（2 秒）', () => {
    const q = createPreopenQueue()
    expect(q.capacity).toBe(PREOPEN_MAX_FRAMES)
    expect(q.capacity).toBe(100)
  })

  it('clear 清空且容量不变', () => {
    const q = createPreopenQueue(5)
    q.push(frame(1))
    q.clear()
    expect(q.size).toBe(0)
    expect(q.capacity).toBe(5)
  })

  it('非法上限收敛到 1', () => {
    const q = createPreopenQueue(0)
    expect(q.capacity).toBe(1)
    q.push(frame(1))
    q.push(frame(2))
    expect(q.drain().map((b) => new Int16Array(b)[0])).toEqual([2])
  })
})
