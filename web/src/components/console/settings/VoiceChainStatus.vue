<template>
  <!-- 语音链路状态条：麦克风 → VAD → KWS → ASR → LLM → TTS → 播放。
       Voice chain: mic → VAD → KWS → ASR → LLM → TTS → playback. -->
  <div class="chain">
    <template v-for="(node, i) in nodes" :key="node.id">
      <button type="button" class="chain-node" :class="node.tone"
              :title="node.reason || node.detail" @click="pick(node)">
        <span class="chain-dot"></span>
        <span class="chain-name">
          <b>{{ node.zh }}</b>
          <i>{{ node.en }}</i>
        </span>
        <span class="chain-detail">{{ node.detail }}</span>
      </button>
      <span v-if="i < nodes.length - 1" class="chain-arrow" aria-hidden="true">→</span>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 链路概览：每个节点显示模块、模式、模型/服务与就绪状态；点击跳到对应 Tab。
 * Chain overview: module, mode, model/service and readiness; clicking jumps to a tab.
 */
import { computed } from 'vue'
import { useConfig } from '../../../composables/useApi'
import { useVoiceModuleStatus } from '../../../composables/useVoiceModuleStatus'
import { ttsSettings } from '../../../composables/assistant/useTts'

const emit = defineEmits<{ select: [tab: 'recognition' | 'synthesis' | 'llm'] }>()

const app = useConfig()
const { status } = useVoiceModuleStatus()

interface Node {
  id: string
  zh: string
  en: string
  detail: string
  reason: string
  tone: 'ok' | 'warn' | 'err' | 'neutral'
  tab?: 'recognition' | 'synthesis' | 'llm'
}

function nodeFrom(kind: 'vad' | 'kws' | 'asr', zh: string, en: string): Node {
  const m = status.value?.[kind]
  if (!m) return { id: kind, zh, en, detail: '未检测 / Unknown', reason: '', tone: 'neutral', tab: 'recognition' }
  const mode = m.mode === 'local' ? '本地 / Local' : m.mode === 'api' ? 'API' : m.mode
  const model = String((m as any).model || (m as any).model_dir || (m as any).local_model || '')
  return {
    id: kind, zh, en,
    detail: `${mode}${model ? ' · ' + model.split(/[\\/]/).pop() : ''}`,
    reason: String(m.reason || ''),
    tone: m.ready ? 'ok' : (m.mode === 'off' ? 'neutral' : 'err'),
    tab: 'recognition',
  }
}

const nodes = computed<Node[]>(() => {
  const micOk = typeof navigator !== 'undefined' && !!navigator.mediaDevices
  const llm = app.config.value
  const tts = status.value?.tts
  const ttsDetail = tts
    ? `${tts.mode === 'local' ? '本地 Kokoro' : 'API'}${tts.ready ? '' : ' · 未就绪'}`
    : '未检测 / Unknown'
  return [
    {
      id: 'mic', zh: '麦克风', en: 'Microphone',
      detail: micOk ? '浏览器输入 / Browser input' : '不可用 / Unavailable',
      reason: '', tone: micOk ? 'ok' : 'err', tab: 'recognition',
    },
    nodeFrom('vad', 'VAD', 'Voice Activity'),
    nodeFrom('kws', 'KWS', 'Keyword'),
    nodeFrom('asr', 'ASR', 'Speech-to-Text'),
    {
      id: 'llm', zh: 'LLM', en: 'Language Model',
      detail: llm?.llm_available ? (llm.llm_profile || 'API') : 'API 未配置',
      reason: '', tone: llm?.llm_available ? 'ok' : 'err', tab: 'llm',
    },
    {
      id: 'tts', zh: 'TTS', en: 'Text-to-Speech',
      detail: ttsDetail, reason: String(tts?.reason || ''),
      tone: tts?.ready ? 'ok' : 'err', tab: 'synthesis',
    },
    {
      id: 'play', zh: '播放', en: 'Playback',
      detail: ttsSettings.value.engine === 'local' ? '本地 Kokoro' : 'API',
      reason: '', tone: tts?.ready ? 'ok' : 'warn', tab: 'synthesis',
    },
  ]
})

function pick(n: Node) {
  if (n.tab) emit('select', n.tab)
}
</script>

<style scoped>
.chain {
  display: flex; align-items: stretch; gap: var(--sp-2);
  flex-wrap: wrap;
}
.chain-node {
  flex: 1 1 110px; min-width: 110px;
  display: flex; flex-direction: column; gap: 2px; align-items: flex-start;
  padding: var(--sp-2) var(--sp-q10);
  border: 1px solid var(--border-soft); border-radius: var(--r-sm);
  background: rgba(15, 23, 42, .55); color: var(--text-2);
  cursor: pointer; text-align: left;
}
.chain-node:hover { border-color: var(--border-base); background: rgba(148, 163, 184, .07); }
.chain-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--text-3); }
.chain-node.ok .chain-dot { background: #34d399; box-shadow: 0 0 6px rgba(52, 211, 153, .6); }
.chain-node.warn .chain-dot { background: #fbbf24; }
.chain-node.err .chain-dot { background: #f87171; box-shadow: 0 0 6px rgba(248, 113, 113, .5); }
.chain-name { display: flex; align-items: baseline; gap: var(--sp-q6); }
.chain-name b { font-size: var(--fs-xs); color: var(--text-1); }
.chain-name i { font-size: var(--fs-2xs); color: var(--text-3); font-style: normal; }
.chain-detail { font-size: var(--fs-2xs); color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.chain-arrow { align-self: center; color: var(--text-3); font-size: var(--fs-2xs); }
</style>
