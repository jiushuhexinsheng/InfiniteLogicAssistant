/**
 * 语音四模块健康状态（来自 /api/voice/capabilities）。
 *
 * Voice module health from /api/voice/capabilities. `ready` is the server's own
 * definition (mode + model presence / API configured), so the menu lights, tabs and
 * overview chain all agree with the backend instead of each re-deriving it.
 */
import { computed, ref } from 'vue'
import { api } from '../api'

export type VoiceModule = 'vad' | 'kws' | 'asr' | 'tts'

export interface VoiceModuleState {
  mode: string
  present: boolean
  ready: boolean
  reason: string
  [key: string]: unknown
}

export const status = ref<Record<VoiceModule, VoiceModuleState> | null>(null)
const loading = ref(false)
const error = ref('')

/** 拉取一次能力状态（设置页/语音页挂载时调用）。Fetch once. */
export async function refreshVoiceStatus(): Promise<void> {
  loading.value = true
  try {
    const r = await api.getCapabilities()
    if (r.ok) {
      status.value = {
        vad: r.vad as VoiceModuleState,
        kws: r.kws as VoiceModuleState,
        asr: r.asr as VoiceModuleState,
        tts: r.tts as VoiceModuleState,
      }
      error.value = ''
    }
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

/** 单模块状态（未拉取时为 undefined）。One module's state. */
export function moduleStatus(kind: VoiceModule): VoiceModuleState | undefined {
  return status.value?.[kind]
}

/** 四模块都就绪（菜单聚合灯用）。All four modules ready (menu aggregate dot). */
export const voiceAllReady = computed(() =>
  !!status.value && (['vad', 'kws', 'asr', 'tts'] as VoiceModule[])
    .every(k => status.value![k].ready))

export function useVoiceModuleStatus() {
  return { status, loading, error, refreshVoiceStatus, moduleStatus, voiceAllReady }
}
