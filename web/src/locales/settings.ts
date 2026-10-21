/**
 * 设置页双语文案表（中文主 / 英文副）。组件只渲染，不在模板里拼文案。
 *
 * Bilingual settings copy (zh primary / en secondary). Components render, never
 * concatenate ad-hoc strings.
 */
export interface BiText {
  zh: string
  en: string
}

export const settingsText = {
  save: { zh: '保存', en: 'Save' },
  saving: { zh: '保存中…', en: 'Saving…' },
  refresh: { zh: '刷新', en: 'Refresh' },
  reset: { zh: '恢复默认', en: 'Reset to Default' },
  add: { zh: '新增', en: 'Add' },
  delete: { zh: '删除', en: 'Delete' },
  change: { zh: '更改', en: 'Change' },
  useLocal: { zh: '一键本地', en: 'Use Local' },
  refreshModels: { zh: '刷新模型', en: 'Refresh Models' },
  scanning: { zh: '扫描中…', en: 'Scanning…' },
  test: { zh: '测试', en: 'Test' },
  testConnection: { zh: '测试连接', en: 'Test Connection' },
  model: { zh: '模型', en: 'Model' },
  modelProvider: { zh: '模型供应商', en: 'Model Provider' },
  local: { zh: '本地', en: 'Local' },
  api: { zh: 'API', en: 'API' },
  acceleration: { zh: '加速后端', en: 'Acceleration' },
  overview: { zh: '概览', en: 'Overview' },
  wake: { zh: '唤醒', en: 'Wake' },
  recognition: { zh: '识别', en: 'Recognition' },
  synthesis: { zh: '合成', en: 'Synthesis' },
  hardware: { zh: '硬件', en: 'Hardware' },
  advanced: { zh: '高级', en: 'Advanced' },
} satisfies Record<string, BiText>
