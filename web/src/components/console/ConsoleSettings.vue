<template>
  <div class="console-settings">
    <div class="cs-head">
      <h2 class="cs-title"><Icon name="settings" :size="17" /> 设置</h2>
      <p class="cs-sub">服务商切换 / 参数调节 / 密钥 / 连接检测 —— 保存后大部分配置即时生效（服务器绑定类需重启）</p>
    </div>

    <!-- 操作条 -->
    <div class="cs-actions">
      <button class="cs-btn primary" :disabled="!editable || saving" @click="save">
        {{ saving ? '保存中…' : '保存' }}
      </button>
      <button class="cs-btn" :disabled="detecting" @click="detectAll">
        {{ detecting ? '检测中…' : '检测全部' }}
      </button>
      <span v-if="msg" class="cs-msg" :class="{ err: isErr(msg) }">{{ msg }}</span>
    </div>
    <div v-if="restartHint" class="cs-restart">{{ restartHint }}</div>

    <!-- 连接状态条 -->
    <div v-if="Object.keys(connResults).length" class="cs-conn">
      <span v-for="c in Object.values(connResults)" :key="c.name" class="cs-conn-chip" :class="'st-' + c.status">
        {{ c.name }} {{ c.status === 'ok' ? '✓ 连通' : c.status === 'skip' ? '跳过' : '✗ 失败' }}
      </span>
    </div>

    <!-- LLM / ASR / TTS -->
    <div v-for="s in sectionDefs" :key="s.key" class="cs-card">
      <div class="cs-card-head">
        <span class="cs-card-title">{{ s.title }}</span>
        <button class="cs-btn sm" @click="detectOne(s.name)">检测连接</button>
      </div>

      <label v-if="s.toggle" class="cs-field row">
        <span class="cs-label">启用</span>
        <input type="checkbox" v-model="sec(s.key).enabled" />
      </label>

      <label class="cs-field">
        <span class="cs-label">服务商 Profile</span>
        <select v-model="sec(s.key).active">
          <option v-for="n in Object.keys(sec(s.key).profiles)" :key="n" :value="n">{{ n }}</option>
        </select>
      </label>

      <template v-for="f in s.fields" :key="f">
        <label class="cs-field">
          <span class="cs-label">{{ fieldLabel(f) }}</span>
          <input
            :type="num(f) ? 'number' : 'text'"
            :step="num(f) ? (f === 'temperature' ? 0.1 : 1) : undefined"
            v-model="sec(s.key).profiles[sec(s.key).active][f]"
          />
        </label>
      </template>

      <div class="cs-keyrow">
        <span class="cs-keybadge" :class="{ set: sec(s.key).api_key_set[sec(s.key).active] }">
          API Key：{{ sec(s.key).api_key_set[sec(s.key).active] ? '已设置' : '未设置' }}
        </span>
        <button class="cs-btn sm" @click="setKey(s.key, sec(s.key).active)">设置</button>
      </div>

      <div v-if="connResults[s.name]" class="cs-connline" :class="'st-' + connResults[s.name].status">
        {{ connResults[s.name].detail || connResults[s.name].status }}
        <em v-if="connResults[s.name].latency_ms != null">{{ connResults[s.name].latency_ms }}ms</em>
      </div>
    </div>

    <!-- 语音：唤醒词 + VAD + 本地播报 -->
    <div class="cs-card">
      <div class="cs-card-head"><span class="cs-card-title">语音（唤醒 / 静音检测）</span></div>
      <label v-if="editable" class="cs-field row">
        <span class="cs-label">唤醒启用</span>
        <input type="checkbox" v-model="editable.wake_word.enabled" />
      </label>
      <label v-if="editable" class="cs-field">
        <span class="cs-label">唤醒词</span>
        <input type="text" v-model="editable.wake_word.keyword" />
      </label>
      <label v-if="editable" class="cs-field">
        <span class="cs-label">灵敏度（0-1）</span>
        <input type="number" step="0.05" min="0" max="1" v-model.number="editable.wake_word.sensitivity" />
      </label>
      <label v-if="editable" class="cs-field">
        <span class="cs-label">静音判定阈值</span>
        <input type="number" step="0.01" v-model.number="editable.vad.silence_threshold" />
      </label>
      <label v-if="editable" class="cs-field">
        <span class="cs-label">静音停止时长（ms）</span>
        <input type="number" v-model.number="editable.vad.silence_duration_ms" />
      </label>
      <label v-if="editable" class="cs-field">
        <span class="cs-label">最长录音（ms）</span>
        <input type="number" v-model.number="editable.vad.max_duration_ms" />
      </label>
      <div class="cs-tts"><TtsSettings /></div>
    </div>

    <!-- 高级设置 -->
    <details class="cs-advanced">
      <summary>高级设置（Agent / LLM 客户端 / 工具 / 服务器 / MCP）</summary>
      <div v-for="s in advancedDefs" :key="s.key" class="cs-card slim">
        <div class="cs-card-head"><span class="cs-card-title">{{ s.title }}</span></div>
        <template v-for="f in s.fields" :key="f[0]">
          <label class="cs-field">
            <span class="cs-label">{{ fieldLabel(f[0]) }}</span>
            <template v-if="f[1] === 'bool'">
              <input type="checkbox" v-model="sec(s.key)[f[0]]" />
            </template>
            <template v-else>
              <input :type="f[1] === 'number' ? 'number' : 'text'" v-model="sec(s.key)[f[0]]" />
            </template>
          </label>
        </template>
      </div>
      <p class="cs-note">
        MCP server 列表、服务器 host/port/api_token 建议直接编辑 config.yaml / config.secrets.yaml（改动需重启生效）。
        密钥只报「已设置 / 未设置」，永不回显。
      </p>
    </details>

    <!-- 配置校验问题 -->
    <div v-if="issues.length" class="cs-issues">
      <p v-for="i in issues" :key="i.key" :class="'lv-' + i.level">[{{ i.level }}] {{ i.key }}：{{ i.message }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Icon from '../Icon.vue'
import TtsSettings from '../assistant/TtsSettings.vue'
import { api } from '../../api'
import type { ConnectivityResult, DetectionIssue, EditableSnapshot } from '../../types'

const editable = ref<EditableSnapshot | null>(null)
const saving = ref(false)
const detecting = ref(false)
const msg = ref('')
const restartHint = ref('')
const connResults = ref<Record<string, ConnectivityResult>>({})
const issues = ref<DetectionIssue[]>([])

// 三大服务 section 定义（name 为 /api/detection 里的连通性结果名）
const sectionDefs = [
  { key: 'llm', name: 'LLM', title: 'LLM 大模型', toggle: false,
    fields: ['endpoint', 'model', 'chat_path', 'max_tokens', 'temperature', 'timeout'] },
  { key: 'asr', name: 'ASR', title: 'ASR 语音识别', toggle: false,
    fields: ['endpoint', 'model', 'language', 'chat_path', 'timeout'] },
  { key: 'tts', name: 'TTS', title: 'TTS 语音合成', toggle: true,
    fields: ['endpoint', 'model', 'voice', 'format', 'chat_path', 'timeout'] },
]

const advancedDefs = [
  { key: 'agent', title: 'Agent 任务执行',
    fields: [['recursion_limit', 'number'], ['multi_agent', 'bool'] as const] },
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
  'silence_duration_ms', 'max_duration_ms', 'recursion_limit', 'retry_max', 'retry_backoff_base',
  'retry_backoff_max', 'circuit_breaker_threshold', 'circuit_breaker_cooldown', 'request_timeout',
  'search_max_results', 'weather_timeout', 'port'])

const LABELS: Record<string, string> = {
  provider: 'Provider', endpoint: 'Endpoint', model: '模型', vision_model: '视觉模型',
  chat_path: 'Chat Path', max_tokens: 'Max Tokens', temperature: 'Temperature', timeout: '超时(s)',
  language: '语言', voice: '音色', format: '格式', recursion_limit: 'ReAct 步数上限',
  multi_agent: '多智能体', retry_max: '重试次数', retry_backoff_base: '退避基数(s)',
  retry_backoff_max: '退避上限(s)', circuit_breaker_threshold: '熔断阈值', circuit_breaker_cooldown: '熔断冷却(s)',
  request_timeout: '请求超时(s)', search_max_results: '搜索结果数', weather_timeout: '天气超时(s)',
  auto_index: '自动建索引', host: 'Host', port: 'Port', open_browser: '启动打开浏览器',
}

function sec(key: string): any {
  return (editable.value as any)?.[key]
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
function statusText(c: ConnectivityResult): string {
  return c.status === 'ok' ? '✓ 连通' : c.status === 'skip' ? '跳过' : '✗ 失败'
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

/** 去掉 *_set 标记，只发可编辑结构（后端 Settings extra=forbid 不接受多余键） */
function stripMeta(e: EditableSnapshot): any {
  const { llm, asr, tts, server, ...rest } = e as any
  return {
    ...rest,
    llm: { active: llm.active, profiles: llm.profiles },
    asr: { active: asr.active, profiles: asr.profiles },
    tts: { enabled: tts.enabled, active: tts.active, profiles: tts.profiles },
    server: { host: server.host, port: server.port, open_browser: server.open_browser, cors_origins: server.cors_origins },
  }
}

async function save() {
  if (!editable.value) return
  saving.value = true
  msg.value = ''
  restartHint.value = ''
  try {
    const r = await api.patchConfig(stripMeta(editable.value))
    if (r.ok) {
      msg.value = r.restart_required ? '已保存（部分设置重启后生效）' : '已保存（已即时生效）'
      restartHint.value = r.restart_required ? '服务器绑定 / MCP 已变更，重启服务后生效' : ''
    } else {
      msg.value = '保存失败: ' + (r.error || '')
    }
  } catch (e: any) {
    msg.value = '保存失败: ' + (e?.message || '')
  } finally {
    saving.value = false
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

/** 设置/清除某服务密钥（path 形如 llm.api_key / llm.profiles.<name>） */
async function setKey(section: string, profile?: string) {
  const path = profile ? `${section}.profiles.${profile}` : `${section}.api_key`
  const label = profile ? `${section} · ${profile}` : section
  const val = window.prompt(`设置 ${label} 的 API Key（留空清除，不回显）：`)
  if (val === null) return
  try {
    const r = await api.putSecret(path, val)
    if (r.ok) {
      msg.value = r.set ? `已设置 ${label} 密钥（即时生效）` : `已清除 ${label} 密钥`
      await load()
    } else {
      msg.value = '设置密钥失败: ' + (r.error || '')
    }
  } catch (e: any) {
    msg.value = '设置密钥失败: ' + (e?.message || '')
  }
}

onMounted(load)
</script>

<style scoped>
.console-settings {
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cs-head { display: flex; flex-direction: column; gap: 4px; }
.cs-title {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: var(--fs-lg); font-weight: 700; letter-spacing: .03em;
  color: var(--text-1); margin: 0;
}
.cs-title :deep(svg) { color: var(--brand-c2); }
.cs-sub { font-size: var(--fs-xs); color: var(--text-3); margin: 0; }

.cs-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.cs-msg { font-size: var(--fs-xs); color: var(--brand-c2); }
.cs-msg.err { color: #f87171; }
.cs-restart {
  font-size: var(--fs-xs); color: #fbbf24;
  background: rgba(251, 191, 36, .08); border: 1px solid rgba(251, 191, 36, .3);
  border-radius: var(--r-sm); padding: 7px 10px;
}

.cs-conn { display: flex; gap: 8px; flex-wrap: wrap; }
.cs-conn-chip {
  font-size: var(--fs-2xs); font-family: var(--font-mono);
  padding: 4px 10px; border-radius: var(--r-full);
  border: 1px solid var(--border-soft); color: var(--text-2);
}
.st-ok { color: #34d399 !important; border-color: rgba(52, 211, 153, .4) !important; background: rgba(52, 211, 153, .07); }
.st-skip { color: var(--text-3) !important; }
.st-fail { color: #f87171 !important; border-color: rgba(248, 113, 113, .4) !important; background: rgba(248, 113, 113, .07); }

.cs-card {
  background: var(--glass-bg-strong);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-2);
  padding: 14px;
  display: flex; flex-direction: column; gap: 10px;
}
.cs-card.slim { padding: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; }
.cs-card-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}

.cs-btn {
  font-size: var(--fs-xs); font-family: var(--font-mono);
  color: var(--text-2); background: rgba(15, 23, 42, .6);
  border: 1px solid var(--border-soft); border-radius: var(--r-full);
  padding: 5px 14px; cursor: pointer;
  transition: color var(--dur-fast), border-color var(--dur-fast), background var(--dur-fast);
}
.cs-btn:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.cs-btn.primary { color: #0b1120; background: linear-gradient(90deg, var(--brand-c2), var(--brand-c3)); border-color: transparent; font-weight: 600; }
.cs-btn.primary:hover { filter: brightness(1.1); }
.cs-btn.sm { font-size: 10px; padding: 3px 10px; }
.cs-btn:disabled { opacity: .5; cursor: not-allowed; }

.cs-field { display: flex; flex-direction: column; gap: 4px; }
.cs-field.row { flex-direction: row; align-items: center; gap: 8px; }
.cs-label {
  font-size: var(--fs-2xs); color: var(--text-3);
  display: flex; justify-content: space-between; align-items: baseline;
}
.cs-field select,
.cs-field input[type="text"],
.cs-field input[type="number"] {
  background: rgba(15, 23, 42, .8); color: var(--text-1);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  font-size: var(--fs-xs); font-family: var(--font-mono);
  padding: 5px 8px; outline: none;
}
.cs-field select:focus,
.cs-field input:focus { border-color: var(--brand-c2); }

.cs-keyrow { display: flex; align-items: center; gap: 8px; }
.cs-keybadge {
  font-size: var(--fs-2xs); font-family: var(--font-mono);
  color: #fbbf24; background: rgba(251, 191, 36, .08);
  border: 1px solid rgba(251, 191, 36, .3); border-radius: var(--r-sm);
  padding: 3px 8px;
}
.cs-keybadge.set { color: #34d399; background: rgba(52, 211, 153, .08); border-color: rgba(52, 211, 153, .3); }

.cs-connline {
  font-size: var(--fs-2xs); color: var(--text-3);
  border-top: 1px dashed var(--border-soft); padding-top: 7px;
}
.cs-connline em { font-style: normal; font-family: var(--font-mono); color: var(--brand-c2); margin-left: 6px; }

.cs-tts { margin-top: 2px; }

.cs-advanced { border-top: 1px dashed var(--border-soft); padding-top: 8px; }
.cs-advanced summary {
  font-size: var(--fs-xs); color: var(--text-3); cursor: pointer;
  padding: 4px 0; user-select: none;
}
.cs-advanced summary:hover { color: var(--brand-c2); }
.cs-advanced .cs-card { margin-top: 10px; }

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
</style>
