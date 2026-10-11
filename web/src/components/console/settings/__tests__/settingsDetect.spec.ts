import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../../api', () => ({
  api: { getDetection: vi.fn() },
}))
vi.mock('../../../../composables/useToast', () => ({
  notify: { ok: vi.fn(), err: vi.fn(), warn: vi.fn(), info: vi.fn(), dismiss: vi.fn(), clear: vi.fn() },
}))

import { api } from '../../../../api'
import { notify } from '../../../../composables/useToast'
import { detectAll, detectOne, detecting, testPassed } from '../detection'
import { editable, menuDot } from '../state'

/**
 * 测试连接反馈（2026-10-11）：结果走 toast（不再占顶部条/卡底行），
 * 成功点亮左侧菜单绿点；绿点语义 = 测过看结果、没测过回退密钥。
 * Connection-test feedback (2026-10-11): results go through toasts (no top bar / card
 * line any more); success lights the left-menu dot. Dot semantics: tested → result wins,
 * untested → key-set fallback.
 */

function reportOf(entries: { name: string; status: string; latency_ms?: number; detail?: string }[]) {
  return { ok: true, report: { connectivity: entries, config: { issues: [] } } }
}

beforeEach(() => {
  vi.clearAllMocks()
  testPassed.value = {}
  editable.value = null as any
})

describe('detectOne 单服务测试', () => {
  it('成功 → notify.ok（含延迟）+ 绿点亮', async () => {
    vi.mocked(api.getDetection).mockResolvedValue(reportOf([
      { name: 'LLM', status: 'ok', latency_ms: 42 },
    ]) as any)
    await detectOne('LLM')
    expect(notify.ok).toHaveBeenCalledWith('LLM 连通正常（42ms）')
    expect(testPassed.value.llm).toBe(true)
    expect(menuDot('llm')).toBe(true)
    expect(detecting.value).toBe(false)
  })

  it('失败 → notify.err + 绿点灭（即便有密钥）', async () => {
    editable.value = { llm: { active: 'p', api_key_set: { p: true } } } as any
    vi.mocked(api.getDetection).mockResolvedValue(reportOf([
      { name: 'LLM', status: 'err', detail: '401 Unauthorized' },
    ]) as any)
    await detectOne('LLM')
    expect(notify.err).toHaveBeenCalled()
    expect(testPassed.value.llm).toBe(false)
    expect(menuDot('llm')).toBe(false)   // 测过 → 结果优先于密钥
  })

  it('未配置跳过 → notify.info，绿点不亮', async () => {
    vi.mocked(api.getDetection).mockResolvedValue(reportOf([
      { name: 'TTS', status: 'skip' },
    ]) as any)
    await detectOne('TTS')
    expect(notify.info).toHaveBeenCalled()
    expect(menuDot('tts')).toBe(false)
  })

  it('请求异常 → notify.err + detecting 复位', async () => {
    vi.mocked(api.getDetection).mockRejectedValue(new Error('net down'))
    await detectOne('LLM')
    expect(notify.err).toHaveBeenCalled()
    expect(detecting.value).toBe(false)
  })
})

describe('detectAll 汇总测试', () => {
  it('全通过 → 汇总 toast + 各模块绿点', async () => {
    vi.mocked(api.getDetection).mockResolvedValue(reportOf([
      { name: 'LLM', status: 'ok' },
      { name: 'ASR', status: 'ok' },
    ]) as any)
    await detectAll()
    expect(notify.ok).toHaveBeenCalledWith('检测完成：2 项全部连通')
    expect(menuDot('llm')).toBe(true)
    expect(menuDot('asr')).toBe(true)
  })

  it('有失败 → 汇总 toast 点名未通过项', async () => {
    vi.mocked(api.getDetection).mockResolvedValue(reportOf([
      { name: 'LLM', status: 'ok' },
      { name: 'ASR', status: 'err' },
    ]) as any)
    await detectAll()
    expect(notify.err).toHaveBeenCalledWith('检测完成：ASR 未通过')
    expect(menuDot('llm')).toBe(true)
    expect(menuDot('asr')).toBe(false)
  })
})

describe('menuDot 绿点语义', () => {
  it('没测过 → 回退「密钥已设置」', () => {
    editable.value = { llm: { active: 'p', api_key_set: { p: true } } } as any
    expect(menuDot('llm')).toBe(true)
    editable.value = { llm: { active: 'p', api_key_set: { p: false } } } as any
    expect(menuDot('llm')).toBe(false)
  })

  it('语音：唤醒启用且有唤醒词 → 绿；关/空词表 → 不绿', () => {
    editable.value = { wake_word: { enabled: true, keywords: ['衍衡'] } } as any
    expect(menuDot('voice')).toBe(true)
    editable.value = { wake_word: { enabled: false, keywords: ['衍衡'] } } as any
    expect(menuDot('voice')).toBe(false)
    editable.value = { wake_word: { enabled: true, keywords: [] } } as any
    expect(menuDot('voice')).toBe(false)
  })

  it('权限与高级设置不设绿点（用户裁定）', () => {
    editable.value = { permissions: {}, advanced: {} } as any
    expect(menuDot('permissions')).toBe(false)
    expect(menuDot('advanced')).toBe(false)
  })
})
