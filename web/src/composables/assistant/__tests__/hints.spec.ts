import { describe, expect, it } from 'vitest'
import { startSubtitle, emptyHint, consoleBanner } from '../hints'

/**
 * 入口提示随唤醒开关走（2026-10-07 遗留审计）：唤醒未开启时，StartPage 副标题、
 * 面板空态、控制台横幅仍叫用户「说唤醒词」——提示与行为不一致（说了也没人听）。
 * 同时把「双击悬浮球开通话」入口补进 StartPage/空态（新交互的门户露出）。
 *
 * Entry prompts follow the wake switch (2026-10-07 leftover audit): with wake disabled the
 * StartPage subtitle, panel empty state and console banner still told the user to say the
 * wake word — copy that contradicts behavior. The double-click call entry is added to the
 * StartPage/empty-state copy as well (first-class exposure of the new interaction).
 */
describe('入口提示随唤醒开关走', () => {
  it('StartPage 副标题：唤醒开 → 保留唤醒提示 + 补双击通话入口', () => {
    const s = startSubtitle(true, '「衍衡」')
    expect(s).toContain('说「衍衡」唤醒')
    expect(s).toContain('双击悬浮球开通话')
  })

  it('StartPage 副标题：唤醒关 → 不叫喊唤醒词，双击通话入口在', () => {
    const s = startSubtitle(false, '「衍衡」')
    expect(s).not.toContain('唤醒')
    expect(s).toContain('双击悬浮球开通话')
    expect(s).toContain('输入文字')
  })

  it('面板空态：唤醒开 → 原句不变（守护）', () => {
    expect(emptyHint(true, '「衍衡」')).toBe('输入文字，或说「衍衡」唤醒')
  })

  it('面板空态：唤醒关 → 不叫喊唤醒词，出路是文字或双击通话', () => {
    const s = emptyHint(false, '「衍衡」')
    expect(s).not.toContain('唤醒')
    expect(s).toContain('双击悬浮球开通话')
  })

  it('控制台横幅：唤醒开 → 原句不变（守护）', () => {
    expect(consoleBanner(true, '「衍衡」')).toBe('在线 · 说「衍衡」唤醒')
  })

  it('控制台横幅：唤醒关 → 不叫喊唤醒词', () => {
    const s = consoleBanner(false, '「衍衡」')
    expect(s).not.toContain('说')
    expect(s).toContain('语音唤醒已关')
  })
})
