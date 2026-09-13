/**
 * 设置页配置元数据：模块 / 字段 / 标签的单一来源，无 Vue 依赖。
 * Settings-page config metadata: the single source of truth for modules, fields
 * and labels. No Vue dependency.
 */

/** 左侧菜单项定义。Left menu item definition. */
export interface MenuDef {
  /** 模块 id（同时是 editable 快照上的 key）。Module id (also the key on the editable snapshot). */
  id: string
  /** 菜单显示名。Menu label. */
  label: string
  /** 图标名。Icon name. */
  icon: string
}

/** 服务模块（LLM / ASR / TTS）定义。Service module (LLM / ASR / TTS) definition. */
export interface SectionDef {
  /** editable 快照上的 key。Key on the editable snapshot. */
  key: string
  /** 连通性结果名（对应 /api/detection）。Connectivity result name (from /api/detection). */
  name: string
  /** 卡片标题。Card title. */
  title: string
  /** 是否有启用开关。Whether an enable toggle is shown. */
  toggle: boolean
  /** 可编辑字段名列表。Editable field names. */
  fields: string[]
}

/** 高级设置子卡定义。Advanced sub-card definition. */
export interface AdvancedDef {
  /** editable 快照上的 key。Key on the editable snapshot. */
  key: string
  /** 子卡标题。Sub-card title. */
  title: string
  /** [字段名, 控件类型] 列表。List of [field name, control type]. */
  fields: readonly (readonly [string, 'number' | 'bool' | 'text'])[]
}

/** 左侧菜单定义。Left menu definitions. */
export const menuDefs: MenuDef[] = [
  { id: 'llm', label: '大模型', icon: 'brain' },
  { id: 'asr', label: '语音识别', icon: 'mic' },
  { id: 'tts', label: '语音合成', icon: 'volume' },
  { id: 'voice', label: '语音唤醒', icon: 'ear' },
  { id: 'permissions', label: '权限', icon: 'shield' },
  { id: 'advanced', label: '高级设置', icon: 'zap' },
]

/** 三大服务 section 定义（name 对应 /api/detection 的连通性结果名）。Three service section definitions (name matches the /api/detection connectivity result name). */
export const sectionDefs: SectionDef[] = [
  { key: 'llm', name: 'LLM', title: 'LLM 大模型', toggle: false,
    fields: ['provider', 'endpoint', 'model', 'chat_path', 'max_tokens', 'temperature', 'timeout'] },
  { key: 'asr', name: 'ASR', title: 'ASR 语音识别', toggle: false,
    fields: ['provider', 'endpoint', 'model', 'language', 'chat_path', 'timeout'] },
  { key: 'tts', name: 'TTS', title: 'TTS 语音合成', toggle: true,
    fields: ['provider', 'endpoint', 'model', 'voice', 'format', 'chat_path', 'timeout'] },
]

/** 高级模块定义（Agent / LLM 客户端 / 工具 / RAG / 服务器）。Advanced module definitions (Agent / LLM client / Tools / RAG / Server). */
export const advancedDefs: AdvancedDef[] = [
  { key: 'agent', title: 'Agent 任务执行',
    fields: [['recursion_limit', 'number'], ['multi_agent', 'bool'], ['structured_temperature', 'number']] },
  { key: 'llm_client', title: 'LLM 客户端（重试 / 熔断）',
    fields: [['retry_max', 'number'], ['retry_backoff_base', 'number'], ['retry_backoff_max', 'number'],
      ['circuit_breaker_threshold', 'number'], ['circuit_breaker_cooldown', 'number'], ['request_timeout', 'number']] },
  { key: 'tools', title: '工具参数',
    fields: [['search_max_results', 'number'], ['weather_timeout', 'number']] },
  { key: 'rag', title: 'RAG 检索', fields: [['auto_index', 'bool']] },
  { key: 'server', title: '服务器',
    fields: [['host', 'text'], ['port', 'number'], ['open_browser', 'bool']] },
]

/** 需要数值类型的字段集合。Set of fields that require numeric input. */
export const NUMERIC = new Set([
  'max_tokens', 'temperature', 'timeout', 'sensitivity', 'silence_threshold',
  'silence_duration_ms', 'max_duration_ms', 'recursion_limit', 'structured_temperature', 'retry_max',
  'retry_backoff_base', 'retry_backoff_max', 'circuit_breaker_threshold', 'circuit_breaker_cooldown',
  'request_timeout', 'search_max_results', 'weather_timeout', 'port',
])

/** 字段中文标签映射。Chinese label mapping for fields. */
export const LABELS: Record<string, string> = {
  provider: '协议', endpoint: 'Endpoint', model: '模型', vision_model: '视觉模型',
  chat_path: 'Chat Path', max_tokens: 'Max Tokens', temperature: 'Temperature', timeout: '超时(s)',
  language: '语言', voice: '音色', format: '格式', recursion_limit: 'ReAct 步数上限',
  multi_agent: '多智能体', structured_temperature: '结构化输出温度', retry_max: '重试次数',
  retry_backoff_base: '退避基数(s)', retry_backoff_max: '退避上限(s)', circuit_breaker_threshold: '熔断阈值',
  circuit_breaker_cooldown: '熔断冷却(s)',
  request_timeout: '请求超时(s)', search_max_results: '搜索结果数', weather_timeout: '天气超时(s)',
  auto_index: '自动建索引', host: 'Host', port: 'Port', open_browser: '启动打开浏览器',
}

/**
 * 根据字段名获取中文标签。
 * Get the Chinese label for a field name.
 *
 * @param f 字段名。Field name.
 * @returns 标签，缺省回退为字段名本身。The label, falling back to the field name itself.
 */
export function fieldLabel(f: string): string {
  return LABELS[f] || f
}

/**
 * 判断字段是否应使用数值输入。
 * Check whether a field should use numeric input.
 *
 * @param f 字段名。Field name.
 * @returns 是否为数值字段。Whether the field is numeric.
 */
export function isNumericField(f: string): boolean {
  return NUMERIC.has(f)
}
