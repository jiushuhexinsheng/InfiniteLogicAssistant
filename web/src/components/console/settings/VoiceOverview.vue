<template>
  <!-- 语音概览仪表盘：就绪结论 + 模式徽章 + 7 张能力卡（输入/理解/输出）+ 只读事实。
       Voice overview dashboard: readiness + mode chips + seven capability tiles
       (input / understanding / output) + read-only facts. -->
  <SettingsCard title="语音总览" title-en="Voice Overview">
    <div class="vo-toolbar">
      <SettingsButton zh="刷新状态" en="Refresh" @click="refresh" />
      <SettingsButton
        class="vo-test-all" zh="测试全部" en="Test all"
        :loading="testingAll" @click="testAll"
      />
    </div>

    <div class="vo-summary">
      <div class="vo-score" :class="scoreTone">
        <b>{{ readyCount }}</b><span>/{{ tiles.length }}</span>
        <em>链路就绪 · Ready</em>
      </div>
      <div class="vo-chips">
        <button
          v-for="chip in modeChips" :key="chip.id" type="button"
          class="vo-chip" :class="`chip-${chip.id}`" @click="emitSelect(chip.tab)"
        >
          <span class="vo-chip-dot" aria-hidden="true"></span>
          <span class="vo-chip-label">{{ chip.label }}</span>
          <span class="vo-chip-value">{{ chip.value }}</span>
        </button>
      </div>
    </div>

    <section v-for="group in groups" :key="group.id" class="vo-group">
      <h4 class="vo-group-title">{{ group.zh }} <i>{{ group.en }}</i></h4>
      <div class="vo-grid">
        <VoiceStatusTile
          v-for="(tile, idx) in group.tiles"
          :key="tile.id"
          :order="tile.order"
          :zh="tile.zh"
          :en="tile.en"
          :detail="tile.detail"
          :tone="tile.tone"
          :mode="tile.mode"
          :reason="tile.reason"
          :arrow="idx < group.tiles.length - 1"
          @select="emitSelect(tile.tab)"
        />
      </div>
      <!-- 层与层之间：一个向下的箭头（最后一层不画）。 -->
      <div v-if="group.id !== 'out'" class="vo-down"><ChainArrow direction="down" /></div>
    </section>

    <p v-if="testSummary" class="vo-test-summary">自检：{{ testSummary }}</p>

    <div class="vo-facts">
      <div class="vo-fact">
        <h5>运行参数 · Runtime</h5>
        <dl>
          <dt>唤醒词</dt><dd>{{ wakeWords || '未配置' }}</dd>
          <dt>ASR 模式</dt><dd>{{ modeLabel(status?.asr?.mode || '') }}</dd>
          <dt>TTS 引擎</dt><dd>{{ ttsSettings.engine === 'local' ? '本地 Kokoro' : 'API' }}</dd>
          <dt>VAD / KWS</dt><dd>{{ modeLabel(status?.vad?.mode || '') }} / {{ modeLabel(status?.kws?.mode || '') }}</dd>
        </dl>
      </div>
      <div class="vo-fact">
        <h5>模型与硬件 · Models &amp; Hardware</h5>
        <dl>
          <dt>模型目录</dt><dd class="mono">models/{vad,kws,asr,tts,llm}</dd>
          <dt>Provider</dt><dd>{{ providers.join(' / ') || 'cpu' }}</dd>
          <dt>sherpa-onnx</dt><dd>{{ hw?.sherpa_version ? `sherpa-onnx ${hw.sherpa_version}` : '—' }}</dd>
          <dt>CPU</dt><dd>{{ hw?.cpu_count ? `${hw.cpu_count} 核` : '—' }}</dd>
        </dl>
      </div>
    </div>
  </SettingsCard>
</template>

<script setup lang="ts">
/**
 * 概览页：把原链路条改成可读的能力卡网格，并给出就绪计数与只读运行信息。
 * `select` 事件由页面处理跳 Tab / 大模型菜单。
 *
 * Overview: replaces the cramped chain strip with capability tiles plus readiness
 * and read-only runtime facts. `select` is handled by the page (tab / LLM menu).
 */
import { computed, onMounted, ref } from 'vue'
import SettingsCard from './SettingsCard.vue'
import SettingsButton from './SettingsButton.vue'
import VoiceStatusTile from './VoiceStatusTile.vue'
import ChainArrow from './ChainArrow.vue'
import { api } from '../../../api'
import { useConfig } from '../../../composables/useApi'
import { useVoiceModuleStatus } from '../../../composables/useVoiceModuleStatus'
import { ttsSettings } from '../../../composables/assistant/useTts'

type Target = 'recognition' | 'synthesis' | 'llm'
const emit = defineEmits<{ select: [target: Target] }>()

const app = useConfig()
const { status, refreshVoiceStatus } = useVoiceModuleStatus()
const hw = ref<any>(null)
const testingAll = ref(false)
const testResults = ref<Record<string, any>>({})

/** 拉取硬件快照（失败静默，事实区显示 —）。Fetch hardware (silent failure). */
async function loadHardware(): Promise<void> {
  try {
    const r = await api.getHardware()
    hw.value = r.hardware
  } catch {
    hw.value = null
  }
}

onMounted(() => { void loadHardware() })

/** 刷新能力状态与硬件。Refresh capability status and hardware. */
function refresh(): void {
  void refreshVoiceStatus()
  void loadHardware()
}

/** 唤醒词列表。Wake words. */
const wakeWords = computed(() => (app.config.value?.wake_word?.keywords || []).join(' / '))

/** 能力 / 服务节点。Capability or service node. */
interface Tile {
  id: string
  order: number
  zh: string
  en: string
  detail: string
  tone: 'ok' | 'warn' | 'err' | 'neutral'
  mode: string
  reason: string
  tab: Target
}

/** 模式中文名（概览只读展示）。Localized mode label. */
function modeLabel(mode: string): string {
  const map: Record<string, string> = {
    local: '本地', cloud: '云端', api: 'API', hybrid: '混合', off: '关闭', text: '文本',
  }
  return map[mode] || mode || '—'
}

/** 本地能力节点（VAD/KWS/ASR）。Local capability node. */
function localTile(kind: 'vad' | 'kws' | 'asr', order: number, zh: string, en: string): Tile {
  const m = status.value?.[kind]
  if (!m) {
    return { id: kind, order, zh, en, detail: '未检测', tone: 'neutral', mode: '', reason: '', tab: 'recognition' }
  }
  const mode = modeLabel(m.mode)
  const model = String((m as any).model || (m as any).model_dir || (m as any).local_model || '')
  // 云端 ASR 用不到本地模型名，避免让人以为本地模型在跑。
  const showModel = model && !(kind === 'asr' && m.mode === 'cloud')
  return {
    id: kind, order, zh, en, mode,
    detail: `${mode}${showModel ? ' · ' + model.split(/[\\/]/).pop() : ''}`,
    tone: m.ready ? 'ok' : (m.mode === 'off' ? 'neutral' : 'err'),
    reason: String(m.reason || ''),
    tab: 'recognition',
  }
}

/** 7 个节点（编号即链路顺序）。Seven nodes in chain order. */
const tiles = computed<Tile[]>(() => {
  const micOk = typeof navigator !== 'undefined' && !!navigator.mediaDevices
  const llm = app.config.value
  const tts = status.value?.tts
  const engine = ttsSettings.value.engine
  return [
    {
      id: 'mic', order: 1, zh: '麦克风', en: 'Microphone', mode: '',
      detail: micOk ? '浏览器输入' : '不可用', tone: micOk ? 'ok' : 'err',
      reason: '', tab: 'recognition',
    },
    localTile('vad', 2, 'VAD', 'Voice Activity'),
    localTile('kws', 3, 'KWS', 'Keyword'),
    localTile('asr', 4, 'ASR', 'Speech-to-Text'),
    {
      id: 'llm', order: 5, zh: 'LLM', en: 'Language Model', mode: 'API',
      detail: llm?.llm_available ? (llm.llm_profile || 'API') : '未配置',
      tone: llm?.llm_available ? 'ok' : 'err', reason: '', tab: 'llm',
    },
    {
      id: 'tts', order: 6, zh: 'TTS', en: 'Text-to-Speech',
      mode: engine === 'local' ? '本地' : 'API',
      detail: tts ? `${engine === 'local' ? '本地 Kokoro' : 'API'}${tts.ready ? '' : ' · 未就绪'}` : '未检测',
      tone: tts?.ready ? 'ok' : 'err', reason: String(tts?.reason || ''), tab: 'synthesis',
    },
    {
      id: 'play', order: 7, zh: '播放', en: 'Playback', mode: '本地',
      detail: engine === 'local' ? '本地 Kokoro' : 'API',
      tone: tts?.ready ? 'ok' : 'warn', reason: '', tab: 'synthesis',
    },
  ]
})

/** 分组（输入 / 理解 / 输出）。Groups. */
const groups = computed(() => [
  { id: 'in', zh: '输入', en: 'Input', tiles: tiles.value.slice(0, 3) },
  { id: 'think', zh: '理解', en: 'Understanding', tiles: tiles.value.slice(3, 5) },
  { id: 'out', zh: '输出', en: 'Output', tiles: tiles.value.slice(5, 7) },
])

/** 就绪数（7 个节点中 ok 的数量）。Ready count. */
const readyCount = computed(() => tiles.value.filter(t => t.tone === 'ok').length)
/** 分数色：全绿 / 部分 / 大面积故障。Score tone. */
const scoreTone = computed(() => {
  if (readyCount.value === tiles.value.length) return 'ok'
  return readyCount.value >= 4 ? 'warn' : 'err'
})

/** 模式徽章（点击跳 Tab）。Mode chips. */
const modeChips = computed<TileChip[]>(() => {
  const s = status.value
  return [
    { id: 'vad', label: 'VAD', value: modeLabel(s?.vad?.mode || ''), tab: 'recognition' },
    { id: 'kws', label: 'KWS', value: modeLabel(s?.kws?.mode || ''), tab: 'recognition' },
    { id: 'asr', label: 'ASR', value: modeLabel(s?.asr?.mode || ''), tab: 'recognition' },
    { id: 'tts', label: 'TTS', value: ttsSettings.value.engine === 'local' ? 'Kokoro' : 'API', tab: 'synthesis' },
  ]
})
interface TileChip { id: string; label: string; value: string; tab: Target }

/** 自检结果摘要。Self-test summary. */
const testSummary = computed(() => {
  const parts: string[] = []
  for (const [kind, r] of Object.entries(testResults.value)) {
    const label = kind.toUpperCase()
    if (r?.ok) parts.push(`${label} ${r.latency_ms != null ? `${r.latency_ms}ms` : 'OK'}`)
    else parts.push(`${label} 失败`)
  }
  return parts.join(' · ')
})

/** 测试全部本地引擎（VAD/KWS/ASR/TTS）。Test all local engines. */
async function testAll(): Promise<void> {
  if (testingAll.value) return
  testingAll.value = true
  try {
    const kinds = ['vad', 'kws', 'asr', 'tts'] as const
    const results = await Promise.allSettled(kinds.map(k => api.testEngine(k)))
    const next: Record<string, any> = {}
    results.forEach((r, i) => {
      next[kinds[i]] = r.status === 'fulfilled' ? r.value : { ok: false }
    })
    testResults.value = next
  } finally {
    testingAll.value = false
  }
}

/** 发跳转事件。Emit navigation. */
function emitSelect(target: Target): void {
  emit('select', target)
}

/** 可用 providers（来自硬件快照）。Available providers. */
const providers = computed<string[]>(() => hw.value?.providers || [])
</script>

<style scoped>
.vo-toolbar { display: flex; align-items: center; gap: var(--sp-1); }
.vo-summary {
  display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap;
  padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border-soft);
  border-radius: var(--r-sm); background: rgba(15, 23, 42, .45);
}
.vo-score { display: flex; align-items: baseline; gap: 2px; color: var(--text-2); }
.vo-score b { font-size: var(--fs-lg); color: var(--text-1); }
.vo-score span { font-size: var(--fs-xs); color: var(--text-3); }
.vo-score em { font-size: var(--fs-2xs); color: var(--text-3); font-style: normal; margin-left: var(--sp-2); }
.vo-score.ok b { color: #34d399; }
.vo-score.warn b { color: #fbbf24; }
.vo-score.err b { color: #f87171; }
.vo-chips { display: flex; gap: var(--sp-2); flex-wrap: wrap; margin-left: auto; }
.vo-chip {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 1px; min-width: 84px; min-height: 44px;
  padding: var(--sp-1) var(--sp-3); border-radius: var(--r-md);
  border: 1px solid var(--border-soft); background: rgba(15, 23, 42, .45);
  color: var(--text-2); cursor: pointer; text-align: center; line-height: 1.3;
}
.vo-chip:hover { border-color: var(--brand-c2); background: rgba(103, 232, 249, .06); }
.vo-chip-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); }
.chip-vad .vo-chip-dot { background: var(--brand-c2); }
.chip-kws .vo-chip-dot { background: #a78bfa; }
.chip-asr .vo-chip-dot { background: #34d399; }
.chip-tts .vo-chip-dot { background: #fbbf24; }
.vo-chip-label { color: var(--text-3); font-size: var(--fs-2xs); letter-spacing: .04em; }
.vo-chip-value { color: var(--text-1); font-size: var(--fs-2xs); }
.vo-group { display: flex; flex-direction: column; gap: var(--sp-2); }
.vo-group-title {
  margin: 0; font-size: var(--fs-2xs); color: var(--text-3);
  letter-spacing: .06em; font-weight: 600;
}
.vo-group-title i { font-style: normal; font-weight: 400; opacity: .75; margin-left: var(--sp-q6); }
.vo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: var(--sp-2); }
.vo-down { display: flex; justify-content: flex-end; padding-right: var(--sp-3); margin-top: -2px; }
.vo-test-summary { margin: 0; font-size: var(--fs-2xs); color: var(--text-3); }
.vo-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--sp-2); }
.vo-fact {
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  padding: var(--sp-2) var(--sp-3); background: rgba(15, 23, 42, .35);
}
.vo-fact h5 { margin: 0 0 var(--sp-2); font-size: var(--fs-2xs); color: var(--text-2); letter-spacing: .04em; }
.vo-fact dl { margin: 0; display: grid; grid-template-columns: 84px 1fr; gap: var(--sp-q6) var(--sp-2); font-size: var(--fs-2xs); }
.vo-fact dt { color: var(--text-3); }
.vo-fact dd { margin: 0; color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vo-fact dd.mono { font-family: var(--font-mono); }
</style>
