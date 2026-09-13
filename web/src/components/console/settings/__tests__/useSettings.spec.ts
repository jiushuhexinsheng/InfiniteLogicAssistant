import { describe, expect, it } from 'vitest'
import { useSettings } from '../useSettings'

/**
 * useSettings() 的公开契约（模块级单例）。
 *
 * 这是重构用的契约测试：6 个子组件都以 `s.xxx` 访问这些成员，拆分内部实现
 * 时任何一个成员丢失都会让组件静默变成 undefined —— 该测试即为此设的护栏。
 *
 * The public contract of useSettings() (module-level singleton).
 *
 * This is a refactoring contract test: all six sub-components access these members
 * as `s.xxx`, so dropping any one during an internal split would silently turn it
 * into undefined in the components. This test is the guard rail for that.
 */

/** 子组件依赖的成员清单（与 useSettings() 的返回键一一对应）。
 *  `app`（全局配置缓存）仅供 state.ts 内部 saveModule 刷新用，无组件消费，故不对外暴露。 */
const EXPECTED_KEYS = [
  'editable', 'saving', 'detecting', 'connResults', 'issues', 'catalog',
  'addingSection', 'customAdding', 'customName', 'activeMenu', 'keyModal', 'showKey',
  'sec', 'ed', 'menuDot',
  'activeProfile', 'vendorPreset', 'vendorList', 'modelOptions', 'voiceOptions', 'presetToProfile',
  'toggleAdding', 'confirmCustom', 'addProfileFromVendor', 'deleteProfile', 'fetchModelsFor',
  'saveModule', 'load', 'detectAll', 'detectOne',
  'openKeyModal', 'keyEnvHint', 'confirmKey', 'clearKey', 'loadCatalog',
] as const

describe('useSettings 公开契约', () => {
  /** 成员齐全：缺任何一个子组件都会拿到 undefined。 */
  it('暴露子组件依赖的全部成员', () => {
    const s = useSettings() as Record<string, unknown>
    for (const key of EXPECTED_KEYS) {
      expect(s, `缺少成员 ${key}`).toHaveProperty(key)
    }
    expect(Object.keys(s).sort()).toEqual([...EXPECTED_KEYS].sort())
  })

  /** 状态成员必须是 ref（有 .value），否则组件里的 s.xxx.value 会崩。 */
  it('状态成员是 ref（具备 .value）', () => {
    const s = useSettings() as Record<string, any>
    for (const key of ['editable', 'saving', 'detecting', 'connResults', 'issues', 'catalog',
      'addingSection', 'customAdding', 'customName', 'activeMenu', 'keyModal', 'showKey']) {
      expect(s[key], `${key} 应为 ref`).toHaveProperty('value')
    }
  })

  /** 函数成员必须是函数。 */
  it('操作成员是函数', () => {
    const s = useSettings() as Record<string, any>
    for (const key of ['sec', 'ed', 'menuDot', 'toggleAdding', 'saveModule', 'load',
      'detectAll', 'detectOne', 'openKeyModal', 'keyEnvHint', 'confirmKey', 'clearKey',
      'loadCatalog', 'fetchModelsFor', 'deleteProfile']) {
      expect(typeof s[key], `${key} 应为函数`).toBe('function')
    }
  })

  /** 模块级单例：两次调用共享同一份 state。 */
  it('两次调用返回同一份状态', () => {
    expect(useSettings().editable).toBe(useSettings().editable)
    expect(useSettings().activeMenu).toBe(useSettings().activeMenu)
  })

  /** 初始值：菜单默认停在「大模型」，配置快照未加载。 */
  it('初始状态：activeMenu 为 llm，editable 为 null', () => {
    const s = useSettings()
    expect(s.activeMenu.value).toBe('llm')
    expect(s.editable.value).toBeNull()
  })
})
