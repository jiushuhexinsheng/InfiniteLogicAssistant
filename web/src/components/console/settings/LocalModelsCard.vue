<template>
  <!-- 本地模型 / 硬件：四能力各自的 local·API 模式、模型下拉、CPU/GPU 与浏览器设备。
       Local models / hardware: per-capability local·API mode, model picker, CPU/GPU and
       browser devices. -->
  <SettingsCard title="本地模型与硬件（sherpa-onnx）">
    <template #actions>
      <UiButton variant="secondary" size="sm" :disabled="loading" @click="oneClickLocal">
        一键本地
      </UiButton>
      <UiButton variant="ghost" size="sm" :disabled="loading" @click="refresh">
        {{ loading ? '扫描中…' : '刷新模型' }}
      </UiButton>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="save">
        {{ s.saving.value ? '保存中…' : '保存' }}
      </UiButton>
    </template>

    <template v-if="s.editable.value">
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

      <!-- 四能力状态：模式 + 模型是否就位；缺失时红色，选错模型一眼可见。 -->
      <div v-if="statusRows.length" class="cs-status">
        <span v-for="row in statusRows" :key="row.kind" class="cs-status-chip" :class="row.tone">
          {{ row.text }}
        </span>
      </div>

      <!-- ── VAD（只有本地，没有云端 VAD）── -->
      <h3 class="cs-title">VAD · 本地分段</h3>
      <SettingsField label="模式" row>
        <UiSegmented
          :model-value="s.ed().vad.mode"
          :options="[{ value: 'local', label: '本地' }, { value: 'off', label: '关闭' }]"
          aria-label="VAD 模式"
          @update:model-value="v => (s.ed().vad.mode = v)"
        />
      </SettingsField>
      <SettingsField label="模型">
        <UiSelect
          :model-value="s.ed().vad.model"
          :options="modelOptions('vad')"
          placeholder="选择 VAD 模型"
          @update:model-value="v => (s.ed().vad.model = String(v))"
        />
        <p class="cs-hint">{{ missingHint('vad', s.ed().vad.model) }}</p>
      </SettingsField>
      <div class="cs-grid">
        <SettingsField label="阈值（0-1）">
          <UiInput type="number" step="0.05" min="0" max="1"
            :model-value="s.ed().vad.vad_threshold"
            @update:model-value="v => (s.ed().vad.vad_threshold = toNum(v))" />
        </SettingsField>
        <SettingsField label="provider">
          <UiSelect :model-value="s.ed().vad.provider" :options="providerOptions"
            @update:model-value="v => (s.ed().vad.provider = String(v))" />
        </SettingsField>
        <SettingsField label="线程（0=自动）">
          <UiInput type="number" min="0" :model-value="s.ed().vad.num_threads"
            @update:model-value="v => (s.ed().vad.num_threads = toNum(v))" />
        </SettingsField>
      </div>

      <!-- ── KWS ── -->
      <h3 class="cs-title">KWS · 唤醒词</h3>
      <SettingsField label="模式" row>
        <UiSegmented
          :model-value="s.ed().kws.mode"
          :options="[
            { value: 'local', label: '本地 KWS' },
            { value: 'api', label: '文本判定' },
            { value: 'off', label: '关闭' },
          ]"
          aria-label="KWS 模式"
          @update:model-value="v => (s.ed().kws.mode = v)"
        />
      </SettingsField>
      <SettingsField v-if="s.ed().kws.mode === 'local'" label="模型">
        <UiSelect
          :model-value="s.ed().kws.model_dir"
          :options="modelOptions('kws')"
          placeholder="选择 KWS 模型"
          @update:model-value="v => (s.ed().kws.model_dir = String(v))"
        />
        <p class="cs-hint">{{ missingHint('kws', s.ed().kws.model_dir) }}</p>
      </SettingsField>
      <div class="cs-grid" v-if="s.ed().kws.mode === 'local'">
        <SettingsField label="provider">
          <UiSelect :model-value="s.ed().kws.provider" :options="providerOptions"
            @update:model-value="v => (s.ed().kws.provider = String(v))" />
        </SettingsField>
        <SettingsField label="线程">
          <UiInput type="number" min="0" :model-value="s.ed().kws.num_threads"
            @update:model-value="v => (s.ed().kws.num_threads = toNum(v))" />
        </SettingsField>
      </div>

      <!-- ── ASR ── -->
      <h3 class="cs-title">ASR · 语音识别</h3>
      <SettingsField label="模式" row>
        <UiSegmented
          :model-value="s.ed().asr.mode"
          :options="[
            { value: 'local', label: '本地' },
            { value: 'cloud', label: 'API' },
            { value: 'hybrid', label: '混合' },
          ]"
          aria-label="ASR 模式"
          @update:model-value="v => (s.ed().asr.mode = v)"
        />
      </SettingsField>
      <SettingsField v-if="s.ed().asr.mode !== 'cloud'" label="本地模型">
        <UiSelect
          :model-value="s.ed().asr.local_model"
          :options="modelOptions('asr')"
          placeholder="选择 ASR 模型"
          @update:model-value="v => (s.ed().asr.local_model = String(v))"
        />
        <p class="cs-hint">{{ missingHint('asr', s.ed().asr.local_model) }}</p>
      </SettingsField>
      <div class="cs-grid" v-if="s.ed().asr.mode !== 'cloud'">
        <SettingsField label="provider">
          <UiSelect :model-value="s.ed().asr.provider" :options="providerOptions"
            @update:model-value="v => (s.ed().asr.provider = String(v))" />
        </SettingsField>
        <SettingsField label="线程（0=自动）">
          <UiInput type="number" min="0" :model-value="s.ed().asr.num_threads"
            @update:model-value="v => (s.ed().asr.num_threads = toNum(v))" />
        </SettingsField>
        <SettingsField label="流式出字" row>
          <UiToggle :model-value="s.ed().asr.streaming"
            @update:model-value="v => (s.ed().asr.streaming = v)" />
        </SettingsField>
      </div>

      <!-- ── TTS ── -->
      <h3 class="cs-title">TTS · 语音合成</h3>
      <p class="cs-hint">引擎选择（浏览器 / 本地 Kokoro / API）在「语音合成」页；这里配置本地 Kokoro 的模型与推理硬件。</p>
      <template v-if="ttsSettings.engine === 'local'">
        <SettingsField label="模型">
          <UiSelect
            :model-value="s.ed().tts.local_model"
            :options="modelOptions('tts')"
            placeholder="选择 TTS 模型"
            @update:model-value="v => (s.ed().tts.local_model = String(v))"
          />
          <p class="cs-hint">{{ missingHint('tts', s.ed().tts.local_model) }}</p>
        </SettingsField>
        <div class="cs-grid">
          <SettingsField label="provider">
            <UiSelect :model-value="s.ed().tts.provider" :options="providerOptions"
              @update:model-value="v => (s.ed().tts.provider = String(v))" />
          </SettingsField>
          <SettingsField label="线程">
            <UiInput type="number" min="0" :model-value="s.ed().tts.num_threads"
              @update:model-value="v => (s.ed().tts.num_threads = toNum(v))" />
          </SettingsField>
          <SettingsField label="音色 ID">
            <UiInput type="number" min="0" :model-value="s.ed().tts.speaker"
              @update:model-value="v => (s.ed().tts.speaker = toNum(v))" />
          </SettingsField>
          <SettingsField label="语速">
            <UiInput type="number" step="0.05" min="0.1" max="4" :model-value="s.ed().tts.speed"
              @update:model-value="v => (s.ed().tts.speed = toNum(v))" />
          </SettingsField>
        </div>
      </template>

      <!-- ── 流式会话 ── -->
      <h3 class="cs-title">流式会话</h3>
      <SettingsField label="启用 WebSocket 流式链路" row>
        <UiToggle :model-value="s.ed().streaming.enabled"
          @update:model-value="v => (s.ed().streaming.enabled = v)" />
      </SettingsField>
      <p class="cs-note">关闭后音频不再走流式链路；新链路不保留旧的浏览器切段上传回退。</p>

      <!-- ── 浏览器硬件 ── -->
      <h3 class="cs-title">麦克风 / 扬声器</h3>
      <div class="cs-grid">
        <SettingsField label="输入设备">
          <UiSelect :model-value="s.ed().hardware.input_device" :options="inputOptions"
            placeholder="系统默认" @update:model-value="v => (s.ed().hardware.input_device = String(v))" />
        </SettingsField>
        <SettingsField label="输出设备">
          <UiSelect :model-value="s.ed().hardware.output_device" :options="outputOptions"
            placeholder="系统默认" @update:model-value="v => (s.ed().hardware.output_device = String(v))" />
        </SettingsField>
      </div>
      <div class="cs-grid">
        <SettingsField label="回声消除" row>
          <UiToggle :model-value="s.ed().hardware.echo_cancellation"
            @update:model-value="v => (s.ed().hardware.echo_cancellation = v)" />
        </SettingsField>
        <SettingsField label="降噪" row>
          <UiToggle :model-value="s.ed().hardware.noise_suppression"
            @update:model-value="v => (s.ed().hardware.noise_suppression = v)" />
        </SettingsField>
        <SettingsField label="自动增益" row>
          <UiToggle :model-value="s.ed().hardware.auto_gain"
            @update:model-value="v => (s.ed().hardware.auto_gain = v)" />
        </SettingsField>
      </div>
      <UiButton variant="secondary" size="sm" @click="refreshDevices(true)">刷新设备列表</UiButton>
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
import { UiButton, UiInput, UiSegmented, UiSelect, UiToggle } from '../../ui'
import { api } from '../../../api'
import { useSettings } from './useSettings'
import { notify } from '../../../composables/useToast'
import { ttsSettings, saveTts } from '../../../composables/assistant/useTts'

const s = useSettings()

/** 已安装模型（按能力）。Installed models by capability. */
const models = ref<Record<string, any[]>>({})
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
const providerOptions = computed(() => providers.value.map((p) => ({ value: p, label: p.toUpperCase() })))

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
  if (mode === 'browser') return { kind: label, text: `${label} 浏览器`, tone: 'info' }
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
  ttsSettings.value.engine = ttsReady ? 'local' : 'browser'
  saveTts()
  if (!ttsReady) notify.warn('Kokoro 本地 TTS 未就位，播报暂用浏览器语音；下载后再次一键本地即可')
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
</style>
