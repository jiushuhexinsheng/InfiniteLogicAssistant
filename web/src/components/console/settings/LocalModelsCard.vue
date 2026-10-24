<template>
  <!-- 本地模型 / 硬件：四能力各自的 local·API 模式、模型下拉、CPU/GPU 与浏览器设备。
       Local models / hardware: per-capability local·API mode, model picker, CPU/GPU and
       browser devices. -->
  <SettingsCard :title="title" :title-en="titleEn">
    <template #actions>
      <template v-if="show('recognition') || show('tts')">
        <UiButton variant="secondary" size="sm" :disabled="loading" @click="oneClickLocal">
          <BiLabel :zh="T.useLocal.zh" :en="T.useLocal.en" />
        </UiButton>
        <UiButton variant="ghost" size="sm" :disabled="loading" @click="refresh">
          <BiLabel :zh="loading ? T.scanning.zh : T.refreshModels.zh"
                   :en="loading ? T.scanning.en : T.refreshModels.en" />
        </UiButton>
      </template>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="save">
        <BiLabel :zh="s.saving.value ? T.saving.zh : T.save.zh"
                 :en="s.saving.value ? T.saving.en : T.save.en" />
      </UiButton>
    </template>

    <template v-if="s.editable.value">
      <template v-if="show('overview') || show('recognition') || show('tts')">
      <p class="cs-note">
        模型目录：<code>models/{vad,kws,asr,tts,llm}</code>。把任意兼容 sherpa-onnx 的模型放进对应目录，
        点「刷新模型」即可选择；大模型可用
        <code>python scripts/fetch_models.py</code> 下载。
      </p>
      <p class="cs-note">
        推理硬件按能力独立选择 —— VAD 跑 CPU、ASR 跑 GPU 是允许的。
        当前可用 provider：<strong>{{ providers.join(' / ') || 'cpu' }}</strong>
        <span v-if="hw">（sherpa-onnx {{ hw.sherpa_version }}，{{ hw.cpu_count }} 核）</span>。
      </p>
      </template>

      <!-- 四能力状态：模式 + 模型是否就位；缺失时红色，选错模型一眼可见。 -->
      <div v-if="statusRows.length && show('recognition')" class="cs-status">
        <span v-for="row in statusRows" :key="row.kind" class="cs-status-chip" :class="row.tone">
          {{ row.text }}
        </span>
      </div>

      <!-- 引擎自检：实际加载并跑一次，给出耗时/结果（模型存在性之外的第二道确认）。 -->
      <div v-if="show('recognition') || show('tts')" class="cs-tests">
        <UiButton
          v-for="k in testKinds" :key="k" variant="secondary" size="sm"
          :disabled="testing === k" @click="testEngine(k)"
        >
          <BiLabel
            :zh="testing === k ? `测试 ${k.toUpperCase()}…` : `测试 ${k.toUpperCase()}`"
            :en="testing === k ? `Testing ${k.toUpperCase()}…` : `Test ${k.toUpperCase()}`"
          />
        </UiButton>
        <template v-for="k in testKinds" :key="`r-${k}`">
          <span v-if="engineTests[k]" class="cs-test-result" :class="{ err: !engineTests[k].ok }">
            {{ k.toUpperCase() }}:
            {{ engineTests[k].ok ? (engineTests[k].detail || 'OK') : (engineTests[k].error || '失败') }}
            <em v-if="engineTests[k].latency_ms != null"> · {{ engineTests[k].latency_ms }}ms</em>
          </span>
        </template>
      </div>

      <!-- ── 识别：VAD / KWS / ASR ── -->
      <template v-if="show('recognition')">
      <h3 class="cs-title">VAD · 本地分段</h3>
      <SourceModeSwitch
        :model-value="s.ed().vad.mode"
        :options="[{ value: 'local', label: '本地', en: 'Local' }, { value: 'off', label: '关闭', en: 'Off' }]"
        label-zh="VAD 模式" label-en="VAD Mode"
        @update:model-value="v => (s.ed().vad.mode = v)"
      />
      <ModelConfigCard
        kind="vad" title-zh="VAD 模型配置" title-en="VAD Model"
        :model-value="s.ed().vad.model"
        :model-options="modelOptions('vad')"
        :values="s.ed().vad"
        :params="schemaFor('vad')"
        :missing-hint="missingHint('vad', s.ed().vad.model)"
        placeholder="选择 VAD 模型 / Select VAD model"
        @update:model="v => switchModel('vad', v)"
      />

      <!-- ── KWS ── -->
      <h3 class="cs-title">KWS · 唤醒词</h3>
      <SourceModeSwitch
        :model-value="s.ed().kws.mode"
        :options="[
          { value: 'local', label: '本地', en: 'Local' },
          { value: 'api', label: '文本', en: 'Text' },
          { value: 'off', label: '关闭', en: 'Off' },
        ]"
        label-zh="KWS 模式" label-en="KWS Mode"
        @update:model-value="v => (s.ed().kws.mode = v)"
      />
      <ModelConfigCard
        v-if="s.ed().kws.mode !== 'off'"
        kind="kws" title-zh="KWS 模型配置" title-en="KWS Model"
        :model-value="s.ed().kws.model_dir"
        :model-options="modelOptions('kws')"
        :values="s.ed().kws"
        :params="schemaFor('kws')"
        :missing-hint="missingHint('kws', s.ed().kws.model_dir)"
        placeholder="选择 KWS 模型 / Select KWS model"
        @update:model="v => switchModel('kws', v)"
      />

      <!-- ── ASR ── -->
      <h3 class="cs-title">ASR · 语音识别</h3>
      <SourceModeSwitch
        :model-value="s.ed().asr.mode"
        :options="[
          { value: 'local', label: '本地', en: 'Local' },
          { value: 'cloud', label: 'API', en: 'API' },
          { value: 'hybrid', label: '混合', en: 'Hybrid' },
        ]"
        label-zh="ASR 模式" label-en="ASR Mode"
        @update:model-value="v => (s.ed().asr.mode = v)"
      />
      <ModelConfigCard
        v-if="s.ed().asr.mode !== 'cloud'"
        kind="asr" title-zh="ASR 模型配置" title-en="ASR Model"
        :model-value="s.ed().asr.local_model"
        :model-options="modelOptions('asr')"
        :values="s.ed().asr"
        :params="schemaFor('asr')"
        :missing-hint="missingHint('asr', s.ed().asr.local_model)"
        placeholder="选择 ASR 模型 / Select ASR model"
        @update:model="v => switchModel('asr', v)"
      />

      </template>

      <!-- ── TTS ── -->
      <template v-if="show('tts')">
      <p class="cs-hint">引擎选择（本地 Kokoro / API）在「合成」Tab 顶部；这里配置本地 Kokoro 的模型与推理硬件。</p>
      <ModelConfigCard
        v-if="ttsSettings.engine === 'local'"
        kind="tts" title-zh="TTS 模型配置" title-en="TTS Model"
        :model-value="s.ed().tts.local_model"
        :model-options="modelOptions('tts')"
        :values="s.ed().tts"
        :params="schemaFor('tts')"
        :missing-hint="missingHint('tts', s.ed().tts.local_model)"
        placeholder="选择 TTS 模型 / Select TTS model"
        @update:model="v => switchModel('tts', v)"
      />

      </template>

      <!-- ── 流式会话 ── -->
      <template v-if="show('advanced')">
      <h3 class="cs-title">流式会话</h3>
      <SettingsField label="启用 WebSocket 流式链路" en="Enable WebSocket streaming" row>
        <UiToggle :model-value="s.ed().streaming.enabled"
          @update:model-value="v => (s.ed().streaming.enabled = v)" />
      </SettingsField>
      <div class="cs-grid">
        <SettingsField label="partial 间隔（ms）" en="Partial interval (ms)">
          <UiInput type="number" min="30" :model-value="s.ed().streaming.partial_interval_ms"
            @update:model-value="v => (s.ed().streaming.partial_interval_ms = toNum(v))" />
        </SettingsField>
        <SettingsField label="端点静音（ms）" en="Endpoint silence (ms)">
          <UiInput type="number" min="100" :model-value="s.ed().streaming.endpoint_silence_ms"
            @update:model-value="v => (s.ed().streaming.endpoint_silence_ms = toNum(v))" />
        </SettingsField>
        <SettingsField label="最长语音（ms）" en="Max utterance (ms)">
          <UiInput type="number" min="1000" :model-value="s.ed().streaming.max_utterance_ms"
            @update:model-value="v => (s.ed().streaming.max_utterance_ms = toNum(v))" />
        </SettingsField>
      </div>
      <p class="cs-note">关闭后音频不再走流式链路；新链路不保留旧的浏览器切段上传回退。</p>
      </template>

      <!-- ── 浏览器硬件 ── -->
      <template v-if="show('hardware')">
      <div class="cs-grid">
        <SettingsField label="输入设备" en="Input device">
          <UiSelect :model-value="s.ed().hardware.input_device" :options="inputOptions"
            placeholder="系统默认 / System default" @update:model-value="v => (s.ed().hardware.input_device = String(v))" />
        </SettingsField>
        <SettingsField label="输出设备" en="Output device">
          <UiSelect :model-value="s.ed().hardware.output_device" :options="outputOptions"
            placeholder="系统默认 / System default" @update:model-value="v => (s.ed().hardware.output_device = String(v))" />
        </SettingsField>
      </div>
      <div class="cs-grid">
        <SettingsField label="回声消除" en="Echo cancellation" row>
          <UiToggle :model-value="s.ed().hardware.echo_cancellation"
            @update:model-value="v => (s.ed().hardware.echo_cancellation = v)" />
        </SettingsField>
        <SettingsField label="降噪" en="Noise suppression" row>
          <UiToggle :model-value="s.ed().hardware.noise_suppression"
            @update:model-value="v => (s.ed().hardware.noise_suppression = v)" />
        </SettingsField>
        <SettingsField label="自动增益" en="Auto gain" row>
          <UiToggle :model-value="s.ed().hardware.auto_gain"
            @update:model-value="v => (s.ed().hardware.auto_gain = v)" />
        </SettingsField>
      </div>
      <UiButton variant="secondary" size="sm" @click="refreshDevices(true)">
        <BiLabel zh="刷新设备列表" en="Refresh devices" />
      </UiButton>
      </template>
    </template>
  </SettingsCard>
</template>

<script setup lang="ts">
/**
 * 本地模型与硬件卡：四能力模式 / 模型 / CPU-GPU / 浏览器设备。
 * Local-models and hardware card: per-capability mode/model/CPU-GPU and browser devices.
 */
import { computed, onMounted, ref } from 'vue'
import SettingsCard from './SettingsCard.vue'
import SettingsField from './SettingsField.vue'
import BiLabel from './BiLabel.vue'
import ModelConfigCard from './ModelConfigCard.vue'
import SourceModeSwitch from './SourceModeSwitch.vue'
import type { SchemaField } from './SchemaForm.vue'
import { UiButton, UiInput, UiSelect, UiToggle } from '../../ui'
import { settingsText as T } from '../../../locales/settings'
import { refreshVoiceStatus } from '../../../composables/useVoiceModuleStatus'
import { api } from '../../../api'
import { useSettings } from './useSettings'
import { notify } from '../../../composables/useToast'
import { ttsSettings, saveTts } from '../../../composables/assistant/useTts'

const s = useSettings()

/** 本卡在「语音」页中的段落；一个组件按 Tab 复用，避免四份重复代码。
 *  Section of this card inside the 语音 page; one component reused per tab. */
const props = withDefaults(defineProps<{
  scope?: 'all' | 'overview' | 'recognition' | 'tts' | 'hardware' | 'advanced'
}>(), { scope: 'all' })

/** 当前段落是否渲染。Whether a section renders in this scope. */
function show(section: string): boolean {
  return props.scope === 'all' || props.scope === section
}

/** 当前 Tab 可测试的引擎。Local engines testable in this scope. */
const testKinds = computed(() => props.scope === 'tts' ? ['tts'] : ['vad', 'kws', 'asr'])

/** 模型切换时按 modelId 保存/恢复模型专属参数（通用参数 provider/线程不随模型走）。
 *  Save/restore model-specific params by modelId; common provider/threads stay shared. */
const MODEL_KEYS: Record<string, string> = {
  vad: 'model', kws: 'model_dir', asr: 'local_model', tts: 'local_model',
}

function switchModel(kind: string, next: string) {
  const e = s.ed()
  if (!e) return
  const key = MODEL_KEYS[kind]
  const old = String(e[kind]?.[key] || '')
  if (old === next) return
  const fields = (schemas.value[kind] || []).filter(f => (f.group || 'model') === 'model')
  if (!e[kind].params) e[kind].params = {}
  if (old) {
    const saved: Record<string, unknown> = {}
    for (const f of fields) saved[f.key] = e[kind][f.key]
    e[kind].params[old] = saved
  }
  // 先按新模型的家族拉 schema（字段/默认值可能不同），再恢复参数。
  // Fetch the new model's schema first (fields/defaults may differ), then restore params.
  void api.getSchema(kind as any, next).then((r) => {
    if (r?.ok) {
      schemas.value[kind] = r.params
      const fresh = r.params.filter((f: SchemaField) => (f.group || 'model') === 'model')
      const saved = e[kind].params?.[next]
      for (const f of fresh) {
        if (saved && Object.prototype.hasOwnProperty.call(saved, f.key)) {
          e[kind][f.key] = saved[f.key]
        } else if (f.default !== undefined) {
          e[kind][f.key] = f.default
        }
      }
    }
  })
  e[kind][key] = next
  engineTests.value = { ...engineTests.value, [kind]: undefined }
}

/** 加载并实际跑一次引擎；结果显示在卡片内。Load and exercise one engine. */
async function testEngine(kind: string) {
  testing.value = kind
  try {
    const r = await api.testEngine(kind as 'vad' | 'kws' | 'asr' | 'tts')
    engineTests.value = { ...engineTests.value, [kind]: r }
    // 自检结果写进后端 _HEALTH 缓存，刷新能力状态让链路条/状态灯即时反映。
    // The self-test writes into the backend _HEALTH cache; refresh so the chain/dots update.
    void refreshVoiceStatus()
    if (r.ok) notify.ok(`${kind.toUpperCase()} 自检通过（${r.latency_ms ?? '?'}ms）`)
    else notify.err(`${kind.toUpperCase()} 自检失败：${r.error || '未知错误'}`)
  } catch (e: any) {
    engineTests.value = { ...engineTests.value, [kind]: { ok: false, error: e?.message || String(e) } }
    notify.err(`${kind.toUpperCase()} 自检失败：${e?.message || e}`)
  } finally {
    testing.value = ''
  }
}

/** 卡片标题随 Tab 变化（中英）。Card title follows the tab (zh/en). */
const title = computed(() => {
  switch (props.scope) {
    case 'overview': return '语音总览'
    case 'recognition': return '识别引擎（VAD / KWS / ASR）'
    case 'tts': return '本地 TTS（Kokoro）'
    case 'hardware': return '麦克风与扬声器'
    case 'advanced': return '流式与高级'
    default: return '本地模型与硬件（sherpa-onnx）'
  }
})
const titleEn = computed(() => {
  switch (props.scope) {
    case 'overview': return 'Voice Overview'
    case 'recognition': return 'Recognition Engine'
    case 'tts': return 'Local TTS'
    case 'hardware': return 'Microphone & Speaker'
    case 'advanced': return 'Streaming & Advanced'
    default: return 'Local Models & Hardware'
  }
})

/** 已安装模型（按能力）。Installed models by capability. */
const models = ref<Record<string, any[]>>({})
/** 后端参数 schema（按能力）。Parameter schema by capability. */
const schemas = ref<Record<string, SchemaField[]>>({})
/** 引擎自检结果（按能力）。Engine self-test results. */
const engineTests = ref<Record<string, any>>({})
const testing = ref('')
/** 硬件快照。Hardware snapshot. */
const hw = ref<any>(null)
/** 四能力状态快照（后端 /api/voice/capabilities）。Four-capability status snapshot. */
const caps = ref<any>(null)
/** 浏览器输入/输出设备。Browser input/output devices. */
const devices = ref<MediaDeviceInfo[]>([])
const loading = ref(false)

/** 可用 provider（含 cpu）。Available providers (cpu included). */
const providers = computed<string[]>(() => {
  const list = (hw.value?.providers || []) as string[]
  if (!list.length) return ['cpu']
  return list.includes('cpu') ? list : ['cpu', ...list]
})
/** 过滤 schema 中的 provider 选项（只保留当前构建真实支持的），并标注推荐后端。 */
function schemaFor(kind: string): SchemaField[] {
  return (schemas.value[kind] || []).map((f) => {
    if (f.key !== 'provider' || !f.options) return f
    const ok = f.options.filter(o => providers.value.includes(String(o.value)))
    const rec = providers.value.includes('cuda') ? 'cuda'
      : providers.value.includes('coreml') ? 'coreml' : 'cpu'
    return {
      ...f,
      options: ok.length ? ok : f.options,
      hint: { zh: `推荐 ${rec.toUpperCase()}`, en: `Recommended: ${rec.toUpperCase()}` },
    }
  })
}

const inputOptions = computed(() => [
  { value: '', label: '系统默认' },
  ...devices.value.filter((d) => d.kind === 'audioinput')
    .map((d, i) => ({ value: d.deviceId, label: d.label || `麦克风 ${i + 1}` })),
])
const outputOptions = computed(() => [
  { value: '', label: '系统默认' },
  ...devices.value.filter((d) => d.kind === 'audiooutput')
    .map((d, i) => ({ value: d.deviceId, label: d.label || `扬声器 ${i + 1}` })),
])

type StatusTone = 'ok' | 'err' | 'info' | 'neutral'
interface StatusRow { kind: string; text: string; tone: StatusTone }

/** 某能力的状态文案。Status text for one capability. */
function capRow(label: string, cap: any, mode: string): StatusRow {
  if (!cap) return { kind: label, text: `${label} —`, tone: 'neutral' }
  if (mode === 'off') return { kind: label, text: `${label} 已关闭`, tone: 'neutral' }
  if (mode === 'cloud' || mode === 'api') {
    return { kind: label, text: `${label} API`, tone: 'info' }
  }
  return cap.present
    ? { kind: label, text: `${label} 本地 ✓`, tone: 'ok' }
    : { kind: label, text: `${label} 本地 · 模型缺失`, tone: 'err' }
}

/** 四能力状态行（随 editable 实时变化）。Live status rows. */
const statusRows = computed<StatusRow[]>(() => {
  const c = caps.value
  const e = s.ed()
  if (!c || !e) return []
  const ttsRow = capRow('TTS', c.tts, e.tts.mode)
  if (e.tts.mode === 'local' && ttsSettings.value.engine !== 'local') {
    ttsRow.text += ' · 播放：浏览器'
  }
  return [
    capRow('VAD', c.vad, e.vad.mode),
    capRow('KWS', c.kws, e.kws.mode),
    capRow('ASR', c.asr, e.asr.mode),
    ttsRow,
  ]
})

/** 模型下拉选项（value = 相对项目根路径）。Model options (value = root-relative path). */
function modelOptions(kind: string) {
  return (models.value[kind] || []).map((m) => ({
    value: m.path,
    label: `${m.name}${m.valid ? '' : '（缺文件）'}`,
  }))
}

/** 缺失文件提示。Missing-files hint. */
function missingHint(kind: string, path: string): string {
  const m = (models.value[kind] || []).find((x) => x.path === path)
  if (!m) return path ? '目录里没有这个模型，点「刷新模型」重新扫描' : ''
  if (m.valid) return ''
  return `缺文件：${(m.missing || []).join('、')}`
}

/** 数值输入：空串保留，其余转 number。Numeric input helper. */
function toNum(v: string): number | '' {
  return v === '' ? '' : Number(v)
}

/** 当前选中模型无效时，自动改用该能力下第一个有效模型（只改表单，不自动保存）。 */
function ensureSelection() {
  const e = s.ed()
  if (!e) return
  const fix = (kind: string, current: string, set: (v: string) => void) => {
    const list = models.value[kind] || []
    if (list.some((m) => m.valid && m.path === current)) return
    const first = list.find((m) => m.valid)
    if (first) set(first.path)
  }
  fix('vad', e.vad.model, (v) => { e.vad.model = v })
  fix('kws', e.kws.model_dir, (v) => { e.kws.model_dir = v })
  fix('asr', e.asr.local_model, (v) => { e.asr.local_model = v })
  fix('tts', e.tts.local_model, (v) => { e.tts.local_model = v })
}

/** 一键本地：四能力切本地并选有效模型；TTS 没有 Kokoro 时保持 API。 */
function oneClickLocal() {
  const e = s.ed()
  if (!e) return
  const valid = (kind: string) => (models.value[kind] || []).filter((m) => m.valid)
  if (!valid('vad').length) {
    notify.err('没有可用的本地 VAD 模型，请先下载或刷新模型')
    return
  }
  if (!valid('asr').length) {
    notify.err('没有可用的本地 ASR 模型，请先下载或刷新模型')
    return
  }
  ensureSelection()
  e.vad.mode = 'local'
  e.kws.mode = valid('kws').length ? 'local' : 'api'
  e.asr.mode = 'local'
  const ttsReady = (models.value.tts || []).some(
    (m) => m.valid && m.path === e.tts.local_model,
  )
  e.tts.mode = ttsReady ? 'local' : 'api'
  ttsSettings.value.engine = ttsReady ? 'local' : 'api'
  saveTts()
  if (!ttsReady) notify.warn('Kokoro 本地 TTS 未就位，TTS 暂用 API；下载后再次一键本地即可')
  notify.ok('已切换为本地语音（保存中）')
  void s.saveModule('models')
}

async function refresh() {
  loading.value = true
  try {
    const [m, h, c] = await Promise.all([
      api.getModels(), api.getHardware(), api.getCapabilities(),
    ])
    if (m.ok) models.value = m.models
    if (h.ok) hw.value = h.hardware
    if (c.ok) caps.value = c
    ensureSelection()
    // 按当前选中的模型拉 schema（字段/默认值随家族变化）。
    // Fetch schema per the currently selected model (fields/defaults vary by family).
    const modelOf = (k: string): string => {
      const e = s.ed()
      return MODEL_KEYS[k] ? String(e?.[k]?.[MODEL_KEYS[k]] || '') : ''
    }
    const schemaResults = await Promise.all(
      (['vad', 'kws', 'asr', 'tts'] as const).map(k =>
        api.getSchema(k, modelOf(k)).catch(() => null)),
    )
    schemaResults.forEach((r, i) => {
      if (r?.ok) schemas.value[['vad', 'kws', 'asr', 'tts'][i]] = r.params
    })
    await refreshDevices(false)
  } catch (e: any) {
    notify.err('模型扫描失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

async function refreshDevices(askPermission = false) {
  try {
    if (askPermission) {
      // 只有用户点「刷新设备列表」才请求权限；打开设置页不弹权限框。
      // Ask for permission only on the explicit refresh click; opening settings must not prompt.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop())
    }
    devices.value = await navigator.mediaDevices.enumerateDevices()
  } catch (e: any) {
    notify.warn('无法读取音频设备：' + (e?.message || e))
  }
}

function save() {
  void s.saveModule('models')
}

onMounted(refresh)
</script>

<style scoped>
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 0; }
.cs-note code, .cs-hint code { font-family: var(--font-mono); }
.cs-hint { font-size: var(--fs-2xs); color: var(--text-3); margin: var(--sp-q6) 0 0; line-height: 1.5; }
.cs-title {
  margin: var(--sp-3) 0 var(--sp-1);
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  padding-top: var(--sp-2); border-top: var(--divider-dashed);
}
.cs-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-2); }
.cs-status { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin: var(--sp-2) 0; }
.cs-status-chip {
  font-size: var(--fs-2xs); line-height: 1.6;
  padding: var(--sp-q6) var(--sp-q10); border-radius: var(--r-full);
  border: 1px solid var(--border-base); color: var(--text-2);
  background: rgba(148, 163, 184, .06);
}
.cs-status-chip.ok { color: #34d399; border-color: rgba(52, 211, 153, .35); background: rgba(52, 211, 153, .08); }
.cs-status-chip.err { color: #f87171; border-color: rgba(248, 113, 113, .4); background: rgba(248, 113, 113, .08); }
.cs-status-chip.info { color: var(--brand-c2); border-color: rgba(103, 232, 249, .3); background: rgba(103, 232, 249, .07); }
.cs-tests { display: flex; align-items: center; flex-wrap: wrap; gap: var(--sp-2); margin: var(--sp-2) 0; }
.cs-test-result { font-size: var(--fs-2xs); color: #34d399; }
.cs-test-result.err { color: #f87171; }
.cs-test-result em { font-style: normal; color: var(--text-3); }
</style>
