// 字段双语标签：中文映射必须是中文，不能与英文重复（如 Endpoint Endpoint）。
import { describe, expect, it } from 'vitest'
import { fieldLabel, fieldLabelEn, sectionDefs } from '../configDefs'

describe('configDefs 双语标签', () => {
  it('三段所有字段的中英标签互不相同', () => {
    for (const def of sectionDefs) {
      for (const f of def.fields) {
        expect(fieldLabel(f), `${f} 中文标签不能与英文相同`).not.toBe(fieldLabelEn(f))
      }
    }
  })

  it('常用字段使用正确中文', () => {
    expect(fieldLabel('endpoint')).toBe('接口地址')
    expect(fieldLabel('chat_path')).toBe('对话路径')
    expect(fieldLabel('max_tokens')).toBe('最大生成 Tokens')
    expect(fieldLabel('temperature')).toBe('温度')
  })
})
