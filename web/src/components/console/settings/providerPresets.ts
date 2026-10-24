/** 供应商预设（仅用于一键预填；不参与保存结构）。Provider presets for quick fill only. */
export type ProviderSection = 'llm' | 'asr' | 'tts'

export interface ProviderPreset {
  id: string
  name: string
  protocol: string
  endpoint: string
  sections: ProviderSection[]
  models?: string[]
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  { id: 'openai', name: 'OpenAI', protocol: 'openai', endpoint: 'https://api.openai.com', sections: ['llm', 'asr', 'tts'] },
  { id: 'deepseek', name: 'DeepSeek', protocol: 'openai', endpoint: 'https://api.deepseek.com', sections: ['llm'], models: ['deepseek-chat', 'deepseek-reasoner'] },
  { id: 'anthropic', name: 'Anthropic', protocol: 'anthropic', endpoint: 'https://api.anthropic.com', sections: ['llm'] },
  { id: 'xiaomi-mimo', name: 'Xiaomi MiMo', protocol: 'openai', endpoint: 'https://token-plan-cn.xiaomimimo.com', sections: ['llm', 'asr', 'tts'] },
]

/** 某 section 可见的预设。Presets visible for a section. */
export function presetsFor(section: ProviderSection): ProviderPreset[] {
  return PROVIDER_PRESETS.filter(p => p.sections.includes(section))
}
