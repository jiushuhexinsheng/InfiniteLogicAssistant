// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

/**
 * 并发 final 去重（docs/designs/10 4.5）。
 *
 * 每段转写都是独立 promise；通话判定（callJudge）要走一次网络往返。前一段的判定
 * 回来得晚时，旧代码仍会把它的文本送进 LLM —— 同一时刻两段话都被执行。修复后
 * 每段 final 认领代际号，异步段结束后校验代际，过期段丢弃。
 *
 * Concurrent final dedupe (docs/designs/10 4.5). Each transcript segment is its own
 * promise and call judging crosses the network; when an older verdict lands late the
 * old code still fed its text to the LLM, executing two utterances at once. Each final
 * now claims a turn generation and re-checks it after async work; stale segments drop.
 */
const callJudge = vi.fn()
vi.mock('../../../api', () => ({
  api: { callJudge: (...a: unknown[]) => callJudge(...a) },
  streamUtter: vi.fn(),
}))

import { handleStreamEvent } from '../stream/streamFlow'
import { st } from '../wake/orchState'
import { callActive, callId, state } from '../store'

describe('streamFlow 并发 final 去重', () => {
  beforeEach(() => {
    callJudge.mockReset()
    st.deps = {
      api: {} as never,
      sendText: vi.fn(),
      sendAnswer: vi.fn(),
      speaking: ref(false),
    }
    callActive.value = true
    callId.value = 'call-1'
    state.value = 'listening'
  })

  it('旧段判定迟到 → 丢弃，只有最新段送 LLM', async () => {
    let releaseFirst!: (v: unknown) => void
    callJudge
      .mockImplementationOnce(() => new Promise((res) => { releaseFirst = res }))
      .mockResolvedValueOnce({ ok: true, hit: true, text: '第二条' })

    const first = handleStreamEvent({ type: 'final', text: '第一条', segment_id: 1, duration_ms: 900, rms: 1 })
    const second = handleStreamEvent({ type: 'final', text: '第二条', segment_id: 2, duration_ms: 900, rms: 1 })
    await second

    releaseFirst({ ok: true, hit: true, text: '第一条' })
    await first

    expect(st.deps!.sendText).toHaveBeenCalledTimes(1)
    expect(st.deps!.sendText).toHaveBeenCalledWith('第二条')
  })
})
