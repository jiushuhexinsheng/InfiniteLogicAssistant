import { beforeEach, describe, expect, it } from 'vitest'
import {
  COMPAT_SHORTCUTS, compatEntries, parseCompatValue, removeCompat, setCompat, toggleCompat,
} from '../profiles'
import { editable } from '../state'

/** 高级兼容编辑（目录退役后的自填闭环）：值类型推断、键改名、快捷项可逆开关。
 * Advanced compat editing (the self-fill loop after the catalogue retired): value type
 * inference, key rename, reversible shortcut toggling. */

const SECTION = { key: 'llm' } as const

function freshSection() {
  editable.value = {
    llm: { active: 'p', profiles: { p: { provider: 'openai' } }, api_key_set: { p: false } },
  } as any
}

describe('高级兼容编辑', () => {
  beforeEach(freshSection)

  it('值类型推断：true/false → 布尔、纯数字 → number、其余字符串', () => {
    expect(parseCompatValue('true')).toBe(true)
    expect(parseCompatValue('false')).toBe(false)
    expect(parseCompatValue('8080')).toBe(8080)
    expect(parseCompatValue('api-key')).toBe('api-key')
    expect(parseCompatValue('v2-chat')).toBe('v2-chat')
  })

  it('setCompat 写入并按推断落类型；改键名保留原值', () => {
    setCompat(SECTION, 'audio_data_url', 'true')
    setCompat(SECTION, 'auth_header', 'api-key')
    const rows = Object.fromEntries(compatEntries(SECTION))
    expect(rows.audio_data_url).toBe('true')
    // 改名：oldKey ≠ key → 删旧建新、值不丢
    setCompat(SECTION, 'auth-header', 'api-key', 'auth_header')
    const after = (editable.value as any).llm.profiles.p.compat
    expect('auth_header' in after).toBe(false)
    expect(after['auth-header']).toBe('api-key')
  })

  it('removeCompat 删除键', () => {
    setCompat(SECTION, 'no_text_parts', 'true')
    removeCompat(SECTION, 'no_text_parts')
    expect(compatEntries(SECTION)).toEqual([])
  })

  it('快捷项可逆：写入 → 再点移除', () => {
    const c = COMPAT_SHORTCUTS.find(x => x.key === 'auth_header')!
    toggleCompat(SECTION, c.key, c.value)
    expect((editable.value as any).llm.profiles.p.compat.auth_header).toBe('api-key')
    toggleCompat(SECTION, c.key, c.value)
    expect('auth_header' in (editable.value as any).llm.profiles.p.compat).toBe(false)
  })

  it('compat 对象缺失时自动初始化（老快照兼容）', () => {
    expect(compatEntries(SECTION)).toEqual([])   // 触发初始化
    setCompat(SECTION, 'stream_options', 'false')
    expect((editable.value as any).llm.profiles.p.compat.stream_options).toBe(false)
  })
})
