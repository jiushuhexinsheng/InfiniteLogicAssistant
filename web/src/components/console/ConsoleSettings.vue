<template>
  <div class="console-settings">
    <div class="cs-head">
      <h2 class="cs-title"><UiIcon name="settings" :size="17" /> 设置</h2>
      <p class="cs-sub">左侧菜单切换模块，每个模块独立「保存 / 测试连接」，密钥通过弹出框设置</p>
    </div>

    <div class="cs-body">
      <!-- 左侧菜单 -->
      <aside class="cs-menu">
        <button
          v-for="m in menuDefs"
          :key="m.id"
          class="cs-menu-item"
          :class="{ on: activeMenu === m.id }"
          @click="activeMenu = m.id"
        >
          <UiIcon :name="m.icon" :size="14" />
          <span>{{ m.label }}</span>
          <i class="cs-menu-dot" :class="{ on: menuDot(m.id) }" title="密钥已设置"></i>
        </button>
        <div class="cs-menu-extra">
          <UiButton variant="secondary" size="sm" :disabled="detecting" @click="detectAll" block>
            {{ detecting ? '检测中…' : '检测全部' }}
          </UiButton>
        </div>
      </aside>

      <!-- 右侧内容 -->
      <div class="cs-main">
        <div v-if="msg" class="cs-msg" :class="{ err: isErr(msg) }">{{ msg }}</div>
        <div v-if="restartHint" class="cs-restart">{{ restartHint }}</div>

        <!-- 连接状态条 -->
        <div v-if="Object.keys(connResults).length" class="cs-conn">
          <UiChip v-for="c in Object.values(connResults)" :key="c.name" :tone="connTone(c.status)" :dot="false">
            {{ c.name }} {{ connStatusText(c.status) }}
          </UiChip>
        </div>

        <!-- 服务模块：LLM / ASR / TTS（activeMenu 对应才显示） -->
        <template v-for="s in sectionDefs" :key="s.key">
          <UiCard v-if="activeMenu === s.key" class="cs-card">
            <div class="cs-card-head">
              <span class="cs-card-title">{{ s.title }}</span>
              <div class="cs-card-btns">
                <UiButton variant="secondary" size="sm" :disabled="detecting" @click="detectOne(s.name)">测试连接</UiButton>
                <UiButton variant="primary" size="sm" :disabled="!editable || saving" @click="saveModule(s.key)">
                  {{ saving ? '保存中…' : '保存' }}
                </UiButton>
              </div>
            </div>

            <SettingsField v-if="s.toggle" label="启用" row>
              <UiToggle :model-value="sec(s.key).enabled" @update:model-value="v => (sec(s.key).enabled = v)" />
            </SettingsField>

            <!-- Profile 管理：切换 / 新增（厂商目录） / 删除 -->
            <div class="cs-profrow">
              <SettingsField label="Profile" grow>
                <UiSelect :model-value="sec(s.key).active" @update:model-value="v => (sec(s.key).active = v)">
                  <option v-for="n in Object.keys(sec(s.key).profiles)" :key="n" :value="n">{{ n }}</option>
                </UiSelect>
              </SettingsField>
              <UiButton variant="secondary" size="sm" :class="{ on: addingSection === s.key }" @click="toggleAdding(s.key)">
                <UiIcon name="plus" :size="12" /> 新增
              </UiButton>
              <UiButton variant="secondary" size="sm" :disabled="Object.keys(sec(s.key).profiles).length <= 1" @click="deleteProfile(s.key)">
                <UiIcon name="trash" :size="12" /> 删除
              </UiButton>
            </div>

            <!-- 厂商目录选择面板（新增 Profile） -->
            <div v-if="addingSection === s.key" class="cs-vendor">
              <p class="cs-vendor-tip">从厂商目录新增 Profile（自动预填端点/模型，可再手动调整）</p>
              <!-- 自定义名称内联输入（替代 window.prompt） -->
              <div v-if="customAdding === s.key" class="cs-vendor-custom">
                <UiInput v-model="customName" placeholder="Profile 名称（如 my-gateway）" @keyup.enter="confirmCustom(s.key)" />
                <UiButton variant="primary" size="sm" @click="confirmCustom(s.key)">创建</UiButton>
                <UiButton variant="secondary" size="sm" @click="customAdding = null">取消</UiButton>
              </div>
              <div v-else class="cs-vendor-grid">
                <button class="cs-vendor-chip custom" @click="customAdding = s.key">＋ 自定义（空白）</button>
                <button v-for="v in vendorList(s.key)" :key="v.id" class="cs-vendor-chip" @click="addProfileFromVendor(s.key, v)">
                  {{ v.label }}
                </button>
              </div>
            </div>

            <template v-for="f in s.fields" :key="f">
              <SettingsField :label="fieldLabel(f)">
                <!-- 协议下拉 -->
                <UiSelect v-if="f === 'provider'" :model-value="sec(s.key).profiles[sec(s.key).active][f]" @update:model-value="v => (sec(s.key).profiles[sec(s.key).active][f] = v)">
                  <option value="openai">OpenAI 兼容</option>
                  <option value="anthropic">Anthropic（原生）</option>
                  <option value="gemini">Gemini（原生）</option>
                </UiSelect>
                <!-- 模型 / 音色可输入下拉 -->
                <template v-else-if="f === 'model' || f === 'voice'">
                  <UiInput :model-value="sec(s.key).profiles[sec(s.key).active][f]" @update:model-value="v => (sec(s.key).profiles[sec(s.key).active][f] = v)" :list="`dl-${s.key}-${f}`" />
                  <datalist :id="`dl-${s.key}-${f}`">
                    <option v-for="m in (f === 'model' ? modelOptions(s) : voiceOptions(s))" :key="m" :value="m" />
                  </datalist>
                </template>
                <UiInput
                  v-else
                  :model-value="sec(s.key).profiles[sec(s.key).active][f]"
                  @update:model-value="v => (sec(s.key).profiles[sec(s.key).active][f] = v)"
                  :type="num(f) ? 'number' : 'text'"
                  :step="num(f) ? (f === 'temperature' ? 0.1 : 1) : undefined"
                />
              </SettingsField>
            </template>

            <div class="cs-keyrow">
              <UiChip :tone="sec(s.key).api_key_set[sec(s.key).active] ? 'ok' : 'warn'" :dot="false">
                API Key：{{ sec(s.key).api_key_set[sec(s.key).active] ? '已设置' : '未设置' }}
              </UiChip>
              <UiButton variant="secondary" size="sm" @click="openKeyModal(s.key, sec(s.key).active)">设置</UiButton>
              <UiButton variant="secondary" size="sm" @click="fetchModelsFor(s.key)">获取模型</UiButton>
            </div>

            <div v-if="connResults[s.name]" class="cs-connline" :class="'st-' + connResults[s.name].status">
              {{ connResults[s.name].detail || connResults[s.name].status }}
              <em v-if="connResults[s.name].latency_ms != null">{{ connResults[s.name].latency_ms }}ms</em>
            </div>
          </UiCard>
        </template>

        <!-- 语音模块：唤醒词 + VAD + 本地播报 -->
        <UiCard v-if="activeMenu === 'voice'" class="cs-card">
          <div class="cs-card-head">
            <span class="cs-card-title">语音（唤醒 / 静音检测）</span>
            <UiButton variant="primary" size="sm" :disabled="!editable || saving" @click="saveModule('voice')">
              {{ saving ? '保存中…' : '保存' }}
            </UiButton>
          </div>
          <SettingsField v-if="editable" label="唤醒启用" row>
            <UiToggle :model-value="ed().wake_word.enabled" @update:model-value="v => (ed().wake_word.enabled = v)" />
          </SettingsField>
          <SettingsField v-if="editable" label="唤醒词">
            <UiInput v-model="ed().wake_word.keyword" />
          </SettingsField>
          <SettingsField v-if="editable" label="灵敏度（0-1）">
            <UiInput type="number" step="0.05" min="0" max="1" :model-value="ed().wake_word.sensitivity" @update:model-value="v => (ed().wake_word.sensitivity = toNum(v))" />
          </SettingsField>
          <SettingsField v-if="editable" label="静音判定阈值">
            <UiInput type="number" step="0.01" :model-value="ed().vad.silence_threshold" @update:model-value="v => (ed().vad.silence_threshold = toNum(v))" />
          </SettingsField>
          <SettingsField v-if="editable" label="静音停止时长（ms）">
            <UiInput type="number" :model-value="ed().vad.silence_duration_ms" @update:model-value="v => (ed().vad.silence_duration_ms = toNum(v))" />
          </SettingsField>
          <SettingsField v-if="editable" label="最长录音（ms）">
            <UiInput type="number" :model-value="ed().vad.max_duration_ms" @update:model-value="v => (ed().vad.max_duration_ms = toNum(v))" />
          </SettingsField>
          <div class="cs-tts"><TtsSettings /></div>
        </UiCard>

        <!-- 高级模块 -->
        <UiCard v-if="activeMenu === 'advanced'" class="cs-card">
          <div class="cs-card-head">
            <span class="cs-card-title">高级设置（Agent / LLM 客户端 / 工具 / 服务器 / MCP）</span>
            <UiButton variant="primary" size="sm" :disabled="!editable || saving" @click="saveModule('advanced')">
              {{ saving ? '保存中…' : '保存' }}
            </UiButton>
          </div>
          <div v-for="s in advancedDefs" :key="s.key" class="cs-subcard">
            <div class="cs-subcard-title">{{ s.title }}</div>
            <template v-for="f in s.fields" :key="f[0]">
              <SettingsField v-if="f[1] === 'bool'" :label="fieldLabel(f[0])" row>
                <UiToggle :model-value="sec(s.key)[f[0]]" @update:model-value="v => (sec(s.key)[f[0]] = v)" />
              </SettingsField>
              <SettingsField v-else :label="fieldLabel(f[0])">
                <UiInput :type="f[1] === 'number' ? 'number' : 'text'" v-model="sec(s.key)[f[0]]" />
              </SettingsField>
            </template>
          </div>
          <p class="cs-note">
            MCP server 列表、服务器 host/port/api_token 建议直接编辑 config.yaml / config.secrets.yaml（改动需重启生效）。
            密钥只报「已设置 / 未设置」，永不回显。
          </p>
        </UiCard>

        <!-- 配置校验问题 -->
        <div v-if="issues.length" class="cs-issues">
          <p v-for="i in issues" :key="i.key" :class="'lv-' + i.level">[{{ i.level }}] {{ i.key }}：{{ i.message }}</p>
        </div>
      </div>
    </div>

    <!-- 密钥弹出框（替代 window.prompt） -->
    <UiModal :model-value="!!keyModal" @update:model-value="v => { if (!v) keyModal = null }" title="设置 API Key">
        <p class="cs-dialog-sub">{{ keyModal?.section }} · {{ keyModal?.profile }}</p>
        <div class="cs-key-input">
          <UiInput
            :type="showKey ? 'text' : 'password'"
            :model-value="keyModal ? keyModal.value : ''"
            @update:model-value="v => { if (keyModal) keyModal.value = v }"
            placeholder="粘贴 API Key（留空 = 清除）"
            autofocus
          />
          <UiButton variant="secondary" size="sm" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</UiButton>
        </div>
        <p v-if="keyEnvHint()" class="cs-dialog-env">
          也可通过环境变量 <code>{{ keyEnvHint() }}</code> 配置（优先级高于此密钥）
        </p>
        <div class="cs-dialog-btns">
          <UiButton variant="ghost" size="sm" @click="clearKey">清除</UiButton>
          <UiButton variant="primary" size="sm" @click="confirmKey">保存</UiButton>
          <UiButton variant="ghost" size="sm" @click="keyModal = null">取消</UiButton>
        </div>
    </UiModal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import TtsSettings from '../assistant/TtsSettings.vue'
import { api } from '../../api'
import { useConfig } from '../../composables/useApi'
import SettingsField from './settings/SettingsField.vue'
import { UiButton, UiCard, UiChip, UiIcon, UiInput, UiModal, UiSelect, UiToggle } from '../ui'
import type { ConnectivityResult, DetectionIssue, EditableSnapshot, ProfileConfig, ProviderPreset } from '../../types'

const app = useConfig()
const editable = ref<EditableSnapshot | null>(null)
const saving = ref(false)
const detecting = ref(false)
const msg = ref('')
const restartHint = ref('')
const connResults = ref<Record<string, ConnectivityResult>>({})
const issues = ref<DetectionIssue[]>([])
// 厂商目录 + 新增 Profile 面板
const catalog = ref<Record<string, ProviderPreset[]> | null>(null)
const addingSection = ref<string | null>(null)
const customAdding = ref<string | null>(null)
const customName = ref('')
// 左侧菜单 + 密钥弹出框
const activeMenu = ref('llm')
const keyModal = ref<{ section: string; profile: string; value: string } | null>(null)
const showKey = ref(false)

const menuDefs = [
  { id: 'llm', label: '大模型', icon: 'brain' },
  { id: 'asr', label: '语音识别', icon: 'mic' },
  { id: 'tts', label: '语音合成', icon: 'volume' },
  { id: 'voice', label: '语音唤醒', icon: 'ear' },
  { id: 'advanced', label: '高级设置', icon: 'zap' },
]

// 三大服务 section 定义（name 为 /api/detection 里的连通性结果名）
const sectionDefs = [
  { key: 'llm', name: 'LLM', title: 'LLM 大模型', toggle: false,
    fields: ['provider', 'endpoint', 'model', 'chat_path', 'max_tokens', 'temperature', 'timeout'] },
  { key: 'asr', name: 'ASR', title: 'ASR 语音识别', toggle: false,
    fields: ['provider', 'endpoint', 'model', 'language', 'chat_path', 'timeout'] },
  { key: 'tts', name: 'TTS', title: 'TTS 语音合成', toggle: true,
    fields: ['provider', 'endpoint', 'model', 'voice', 'format', 'chat_path', 'timeout'] },
]

const advancedDefs = [
  { key: 'agent', title: 'Agent 任务执行',
    fields: [['recursion_limit', 'number'], ['multi_agent', 'bool'], ['structured_temperature', 'number'] as const] },
  { key: 'llm_client', title: 'LLM 客户端（重试 / 熔断）',
    fields: [['retry_max', 'number'], ['retry_backoff_base', 'number'], ['retry_backoff_max', 'number'],
      ['circuit_breaker_threshold', 'number'], ['circuit_breaker_cooldown', 'number'], ['request_timeout', 'number']] },
  { key: 'tools', title: '工具参数',
    fields: [['search_max_results', 'number'], ['weather_timeout', 'number']] },
  { key: 'rag', title: 'RAG 检索', fields: [['auto_index', 'bool'] as const] },
  { key: 'server', title: '服务器',
    fields: [['host', 'text'], ['port', 'number'], ['open_browser', 'bool'] as const] },
]

const NUMERIC = new Set(['max_tokens', 'temperature', 'timeout', 'sensitivity', 'silence_threshold',
  'silence_duration_ms', 'max_duration_ms', 'recursion_limit', 'structured_temperature', 'retry_max',
  'retry_backoff_base', 'retry_backoff_max', 'circuit_breaker_threshold', 'circuit_breaker_cooldown',
  'request_timeout', 'search_max_results', 'weather_timeout', 'port'])

const LABELS: Record<string, string> = {
  provider: '协议', endpoint: 'Endpoint', model: '模型', vision_model: '视觉模型',
  chat_path: 'Chat Path', max_tokens: 'Max Tokens', temperature: 'Temperature', timeout: '超时(s)',
  language: '语言', voice: '音色', format: '格式', recursion_limit: 'ReAct 步数上限',
  multi_agent: '多智能体', structured_temperature: '结构化输出温度', retry_max: '重试次数',
  retry_backoff_base: '退避基数(s)', retry_backoff_max: '退避上限(s)', circuit_breaker_threshold: '熔断阈值',
  circuit_breaker_cooldown: '熔断冷却(s)',
  request_timeout: '请求超时(s)', search_max_results: '搜索结果数', weather_timeout: '天气超时(s)',
  auto_index: '自动建索引', host: 'Host', port: 'Port', open_browser: '启动打开浏览器',
}

function sec(key: string): any {
  return (editable.value as any)?.[key]
}
/** 语音模块顶层对象（wake_word / vad 不在模块 key 下，直接挂在 editable 根） */
function ed(): any {
  return editable.value
}
function fieldLabel(f: string): string {
  return LABELS[f] || f
}
function num(f: string): boolean {
  return NUMERIC.has(f)
}
function isErr(m: string): boolean {
  return m.includes('失败') || m.includes('无效')
}
function connTone(status: string): 'ok' | 'warn' | 'err' | 'info' | 'neutral' {
  return status === 'ok' ? 'ok' : status === 'skip' ? 'neutral' : 'err'
}
function connStatusText(status: string): string {
  return status === 'ok' ? '✓ 连通' : status === 'skip' ? '跳过' : '✗ 失败'
}
/** 数值输入：保留空串（清空），其余转 number（与原生 v-model.number 行为一致） */
function toNum(v: string): number | '' {
  return v === '' ? '' : Number(v)
}

// ─── 菜单状态点：服务模块显示「密钥已设置」绿点 ───

function menuDot(id: string): boolean {
  if (id === 'llm' || id === 'asr' || id === 'tts') {
    const s = (editable.value as any)?.[id]
    return !!s?.api_key_set?.[s.active]
  }
  return false
}

// ─── 厂商目录 / Profile 管理 ───

function activeProfile(s: any): ProfileConfig {
  return (editable.value as any)?.[s.key]?.profiles?.[(editable.value as any)[s.key].active] || {}
}
function vendorPreset(s: any): ProviderPreset | null {
  const prof = activeProfile(s)
  if (!prof.vendor || !catalog.value) return null
  return catalog.value[s.key]?.find((v) => v.id === prof.vendor) || null
}
function vendorList(key: string): ProviderPreset[] {
  return (catalog.value && catalog.value[key]) || []
}
function modelOptions(s: any): string[] {
  const prof = activeProfile(s)
  const v = vendorPreset(s)
  return [...new Set([...(prof.models || []), ...(v?.models || [])])].filter(Boolean)
}
function voiceOptions(s: any): string[] {
  const prof = activeProfile(s)
  const v = vendorPreset(s)
  return [...new Set([...(prof.voices || []), ...(v?.voices || [])])].filter(Boolean)
}
/** 目录预设 → 可编辑 profile（与后端 core/providers.preset_to_profile 对齐） */
function presetToProfile(v: ProviderPreset): ProfileConfig {
  const p: any = {
    provider: v.provider || 'openai',
    vendor: v.id,
    endpoint: v.endpoint,
    chat_path: v.chat_path || '/v1/chat/completions',
    models: [...v.models],
    model: v.defaults?.model || v.models[0] || '',
    api_key_env: v.api_key_env,
    compat: { ...v.compat },
  }
  if (v.models_path) p.models_path = v.models_path
  if (v.vision_models?.length) p.vision_model = v.vision_models[0]
  if (v.voices?.length) {
    p.voices = [...v.voices]
    p.voice = v.defaults?.voice || v.voices[0]
  }
  for (const [k, val] of Object.entries(v.defaults || {})) {
    if (p[k] === undefined) p[k] = val
  }
  return p
}

function toggleAdding(key: string) {
  addingSection.value = addingSection.value === key ? null : key
  customAdding.value = null
}

/** 按模块产出 PATCH body（service: 只该 section；voice: 唤醒+VAD；advanced: 全部高级段） */
function moduleBody(id: string): Record<string, any> {
  const e = editable.value as any
  if (id === 'voice') return { wake_word: e.wake_word, vad: e.vad }
  if (id === 'advanced') {
    return {
      agent: e.agent,
      llm_client: e.llm_client,
      tools: e.tools,
      rag: e.rag,
      server: { host: e.server.host, port: e.server.port, open_browser: e.server.open_browser, cors_origins: e.server.cors_origins },
      mcp: e.mcp,
    }
  }
  if (id === 'tts') return { tts: { enabled: e.tts.enabled, active: e.tts.active, profiles: e.tts.profiles } }
  return { [id]: { active: e[id].active, profiles: e[id].profiles } }
}

/** 只持久化单个模块（新增/删除 Profile 用，静默不弹提示） */
async function persistSection(key: string): Promise<boolean> {
  if (!editable.value) return false
  try {
    const r = await api.patchConfig(moduleBody(key))
    return !!r.ok
  } catch {
    return false
  }
}

/** 自定义空白 Profile：内联输入取名 → 建空 profile（provider=openai + 默认 chat_path）并立即保存 */
async function confirmCustom(key: string) {
  const name = customName.value.trim() || 'custom'
  const profiles = (editable.value as any)[key].profiles
  if (profiles[name]) { msg.value = `Profile「${name}」已存在`; return }
  profiles[name] = { provider: 'openai', chat_path: '/v1/chat/completions', models: [] }
  ;(editable.value as any)[key].active = name
  customAdding.value = null
  customName.value = ''
  const ok = await persistSection(key)
  msg.value = ok
    ? `已添加并保存空白 Profile「${name}」，请填写 endpoint/模型 并设置 API Key`
    : `已添加 Profile「${name}」（保存失败，请检查后手动保存）`
}

async function addProfileFromVendor(key: string, v: ProviderPreset) {
  const profiles = (editable.value as any)[key].profiles
  let name = v.id
  let i = 2
  while (profiles[name]) name = `${v.id}-${i++}`
  profiles[name] = presetToProfile(v)
  ;(editable.value as any)[key].active = name
  addingSection.value = null
  const ok = await persistSection(key)
  msg.value = ok
    ? `已添加并保存 Profile「${name}」，请设置 API Key`
    : `已添加 Profile「${name}」（保存失败，请检查后手动保存）`
}

async function deleteProfile(key: string) {
  const s = (editable.value as any)[key]
  const names = Object.keys(s.profiles)
  if (names.length <= 1) { msg.value = '至少保留一个 Profile'; return }
  const name = s.active
  if (!window.confirm(`删除 Profile「${name}」？`)) return
  delete s.profiles[name]
  const rest = Object.keys(s.profiles)
  if (!rest.includes(s.active)) s.active = rest[0]
  const ok = await persistSection(key)
  msg.value = ok ? `已删除 Profile「${name}」` : `已删除 Profile「${name}」（保存失败，请检查）`
}

/** 拉取当前 profile 的模型列表（openai/anthropic/gemini 均支持），写回 profile.models */
async function fetchModelsFor(s: any) {
  const prof = activeProfile(s)
  const profile = { name: (editable.value as any)[s.key].active, ...prof }
  msg.value = ''
  try {
    const r = await api.fetchModels(s.key, profile)
    if (r.ok) {
      prof.models = r.models
      if (r.models.length && (!prof.model || !r.models.includes(prof.model))) prof.model = r.models[0]
      msg.value = `已获取 ${r.count} 个模型`
    } else {
      msg.value = '获取模型失败: ' + (r.error || '')
    }
  } catch (e: any) {
    msg.value = '获取模型失败: ' + (e?.message || '')
  }
}

// ─── 模块级保存 / 测试 ───

async function saveModule(id: string) {
  if (!editable.value) return
  saving.value = true
  msg.value = ''
  restartHint.value = ''
  try {
    const r = await api.patchConfig(moduleBody(id))
    if (r.ok) {
      msg.value = r.restart_required ? '已保存（部分设置重启后生效）' : '已保存（已即时生效）'
      restartHint.value = r.restart_required ? '服务器绑定 / MCP 已变更，重启服务后生效' : ''
      // 刷新全局 /api/config 缓存，让 tts_available / 当前 profile 等即时更新（无需刷新页面）
      app.refreshConfig()
    } else {
      msg.value = '保存失败: ' + (r.error || '')
    }
  } catch (e: any) {
    msg.value = '保存失败: ' + (e?.message || '')
  } finally {
    saving.value = false
  }
}

async function load() {
  try {
    const r = await api.getConfigFull()
    if (r.ok && r.editable) {
      editable.value = r.editable
      // 若当前 active profile 不在 profiles（可能被清），回退到第一个
      for (const key of ['llm', 'asr', 'tts'] as const) {
        const s: any = r.editable[key]
        if (s && !s.profiles[s.active] && Object.keys(s.profiles).length) {
          s.active = Object.keys(s.profiles)[0]
        }
      }
    } else {
      msg.value = '加载配置失败'
    }
  } catch (e: any) {
    msg.value = '加载配置失败: ' + (e?.message || '')
  }
}

async function detectAll() {
  detecting.value = true
  issues.value = []
  try {
    const r = await api.getDetection()
    if (r.ok && r.report) {
      connResults.value = Object.fromEntries(r.report.connectivity.map((c) => [c.name, c]))
      issues.value = r.report.config.issues
    } else {
      msg.value = '检测失败: ' + (r as any)?.error || ''
    }
  } catch (e: any) {
    msg.value = '检测失败: ' + (e?.message || '')
  } finally {
    detecting.value = false
  }
}

async function detectOne(name: string) {
  detecting.value = true
  try {
    const r = await api.getDetection()
    if (r.ok) {
      const c = r.report.connectivity.find((x) => x.name === name)
      if (c) connResults.value = { ...connResults.value, [name]: c }
    }
  } catch {
    /* 静默 */
  } finally {
    detecting.value = false
  }
}

// ─── 密钥弹出框（替代 window.prompt） ───

function openKeyModal(section: string, profile: string) {
  showKey.value = false
  keyModal.value = { section, profile, value: '' }
}
function keyEnvHint(): string {
  const m = keyModal.value
  if (!m) return ''
  return (editable.value as any)?.[m.section]?.profiles?.[m.profile]?.api_key_env || ''
}
async function confirmKey() {
  const m = keyModal.value
  if (!m) return
  const path = `${m.section}.profiles.${m.profile}`
  const label = `${m.section} · ${m.profile}`
  try {
    const r = await api.putSecret(path, m.value)
    if (r.ok) {
      msg.value = r.set ? `已设置 ${label} 密钥（即时生效）` : `已清除 ${label} 密钥`
      const sec = (editable.value as any)?.[m.section]
      if (sec?.api_key_set) sec.api_key_set[m.profile] = r.set
      keyModal.value = null
    } else {
      msg.value = '设置密钥失败: ' + (r.error || '')
    }
  } catch (e: any) {
    msg.value = '设置密钥失败: ' + (e?.message || '')
  }
}
async function clearKey() {
  const m = keyModal.value
  if (!m) return
  m.value = ''
  await confirmKey()
}

async function loadCatalog() {
  try {
    const r = await api.getProviders()
    if (r.ok) catalog.value = r.catalog
  } catch { /* 目录拉取失败不阻塞设置页 */ }
}

onMounted(() => { load(); loadCatalog() })
</script>

<style scoped>
.console-settings {
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px; flex: 1; min-height: 0; overflow-y: auto;}
.cs-head { display: flex; flex-direction: column; gap: 4px; }
.cs-title {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: var(--fs-lg); font-weight: 700; letter-spacing: .03em;
  color: var(--text-1); margin: 0;
}
.cs-title :deep(svg) { color: var(--brand-c2); }
.cs-sub { font-size: var(--fs-xs); color: var(--text-3); margin: 0; }

/* ── 左菜单 + 右内容 ── */
.cs-body { display: flex; gap: 16px; align-items: flex-start; }
.cs-menu {
  width: 148px; flex-shrink: 0; position: sticky; top: 12px;
  display: flex; flex-direction: column; gap: 3px;
}
.cs-menu-item {
  display: flex; align-items: center; gap: 8px;
  font-size: var(--fs-xs); color: var(--text-2); text-align: left;
  background: rgba(15, 23, 42, .55); border: 1px solid transparent;
  border-radius: var(--r-sm); padding: 7px 10px; cursor: pointer;
  transition: color var(--dur-fast), border-color var(--dur-fast), background var(--dur-fast);
}
.cs-menu-item:hover { color: var(--brand-c2); }
.cs-menu-item.on {
  color: var(--brand-c2); border-color: var(--brand-c2);
  background: rgba(11, 17, 32, .75);
}
.cs-menu-dot {
  margin-left: auto; width: 7px; height: 7px; border-radius: 50%;
  background: rgba(148, 163, 184, .25);
}
.cs-menu-dot.on { background: #34d399; box-shadow: 0 0 6px rgba(52, 211, 153, .6); }
.cs-menu-extra { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border-soft); }

.cs-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }

.cs-restart {
  font-size: var(--fs-xs); color: #fbbf24;
  background: rgba(251, 191, 36, .08); border: 1px solid rgba(251, 191, 36, .3);
  border-radius: var(--r-sm); padding: 7px 10px;
}
.cs-msg { font-size: var(--fs-xs); color: var(--brand-c2); }
.cs-msg.err { color: #f87171; }

.cs-conn { display: flex; gap: 8px; flex-wrap: wrap; }
.st-ok { color: #34d399 !important; border-color: rgba(52, 211, 153, .4) !important; background: rgba(52, 211, 153, .07); }
.st-skip { color: var(--text-3) !important; }
.st-fail { color: #f87171 !important; border-color: rgba(248, 113, 113, .4) !important; background: rgba(248, 113, 113, .07); }

.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}
.cs-card-btns { display: flex; align-items: center; gap: 8px; }

.cs-profrow { display: flex; align-items: flex-end; gap: 8px; }

.cs-vendor {
  border: 1px dashed var(--border-soft); border-radius: var(--r-sm);
  padding: 8px 10px; background: rgba(15, 23, 42, .4);
}
.cs-vendor-tip { font-size: var(--fs-2xs); color: var(--text-3); margin: 0 0 7px; }
.cs-vendor-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.cs-vendor-chip {
  font-size: var(--fs-2xs); font-family: var(--font-mono); color: var(--text-2);
  background: rgba(15, 23, 42, .6); border: 1px solid var(--border-soft);
  border-radius: var(--r-full); padding: 3px 10px; cursor: pointer;
}
.cs-vendor-chip:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.cs-vendor-chip.custom { border-style: dashed; color: var(--brand-c2); }
.cs-vendor-custom { display: flex; align-items: center; gap: 8px; }

.cs-keyrow { display: flex; align-items: center; gap: 8px; }

/* 输入框在 flex 行里占满剩余空间（UiInput 默认 width:100%） */
.cs-vendor-custom :deep(.ui-input),
.cs-key-input :deep(.ui-input) { flex: 1; min-width: 0; }

.cs-connline {
  font-size: var(--fs-2xs); color: var(--text-3);
  border-top: 1px dashed var(--border-soft); padding-top: 7px;
}
.cs-connline em { font-style: normal; font-family: var(--font-mono); color: var(--brand-c2); margin-left: 6px; }

.cs-tts { margin-top: 2px; }

.cs-subcard {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft); border-radius: var(--r-md);
  background: rgba(15, 23, 42, .4);
}
.cs-subcard-title {
  font-size: var(--fs-xs); font-weight: 600; color: var(--text-2);
  letter-spacing: .02em;
}

/* 新增 Profile 按钮激活态（UiButton 透传 class） */
.cs-profrow :deep(.ui-btn.on) { color: var(--brand-c2); border-color: var(--brand-c2); }

.cs-issues { display: flex; flex-direction: column; gap: 6px; }
.cs-issues p {
  font-size: var(--fs-2xs); margin: 0; line-height: 1.5;
  border-radius: var(--r-sm); padding: 6px 9px;
}
.lv-error { color: #f87171; background: rgba(248, 113, 113, .07); }
.lv-warning { color: #fbbf24; background: rgba(251, 191, 36, .07); }
.lv-info { color: var(--text-3); background: rgba(148, 163, 184, .07); }

.cs-note {
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6;
  margin: 4px 0 0;
}

/* ── 密钥弹出框 ── */
.cs-dialog-sub { font-size: var(--fs-2xs); color: var(--text-3); margin: 0; font-family: var(--font-mono); }
.cs-key-input { display: flex; align-items: center; gap: 8px; }
.cs-dialog-env { font-size: var(--fs-2xs); color: var(--text-3); margin: 0; line-height: 1.6; }
.cs-dialog-env code { font-family: var(--font-mono); color: var(--brand-c2); }
.cs-dialog-btns { display: flex; justify-content: flex-end; gap: 8px; }
</style>
