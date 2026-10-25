// 识别结果去向（HUD）：已接受给 LLM / 旁白 / 新一段重置。
import { beforeEach, describe, expect, it } from 'vitest'
import {
  beginRecognition, clearTranscript, finalizeTranscript, hudOutcome,
  markHudAccepted, markHudDropped, showGhost,
} from '../storeTranscript'

describe('storeTranscript HUD 去向', () => {
  beforeEach(() => clearTranscript())

  it('初始为 idle；标记接受后变为 accepted', () => {
    expect(hudOutcome.value).toBe('idle')
    markHudAccepted()
    expect(hudOutcome.value).toBe('accepted')
  })

  it('定稿先进入 pending，判定后进入 accepted / dropped', () => {
    finalizeTranscript('查天气', 1)
    expect(hudOutcome.value).toBe('pending')

    markHudDropped()
    expect(hudOutcome.value).toBe('dropped')

    markHudAccepted()
    expect(hudOutcome.value).toBe('accepted')
  })

  it('旁白设为 ghost；新一段识别重置为 idle', () => {
    showGhost('电视里的声音')
    expect(hudOutcome.value).toBe('ghost')
    beginRecognition(1)
    expect(hudOutcome.value).toBe('idle')
  })
})
