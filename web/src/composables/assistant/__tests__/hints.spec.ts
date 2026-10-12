import { describe, expect, it } from 'vitest'
import { startSubtitle, emptyHint } from '../hints'

/**
 * 入口提示随唤醒开关走（2026-10-07 遗留审计）：唤醒未开启时，StartPage 副标题、
 * 面板空态仍叫用户「说唤醒词」——提示与行为不一致（说了也没人听）。
 * 同时把「双击悬浮球开通话」入口补进 StartPage/空态（新交互的门户露出）。
 * （控制台横幅已随 2026-10-11 对话页改版移除，相关用例删除。）
 *
 * Entry prompts follow the wake switch (2026-10-07 leftover audit): with wake disabled the
 * StartPage subtitle and panel empty state still told the user to say the wake word — copy
 * that contradicts behavior. The double-click call entry is added to the StartPage/empty-state
 * copy as well. (The console banner went away with the 2026-10-11 conversation rework; its
 * cases were removed with it.)
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
})
