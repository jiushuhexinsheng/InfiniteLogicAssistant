import { ref } from 'vue'
import { api } from '../api'
import type { ConfigResponse } from '../types'

/** 模块级单例配置 —— 全站共享一份 config（悬浮球 / 开始页 / 控制台）。Module-level singleton config —— a shared config instance across the entire site (floating ball / start page / console). */
const config = ref<ConfigResponse | null>(null)
/** 配置请求的 Promise，用于实现请求单飞。Promise for config request, used to implement request deduplication. */
let configPromise: Promise<void> | null = null

/** 拉取 /api/config（单飞幂等：并发调用共享一次请求，完成后可再次刷新）。Fetch /api/config (idempotent with deduplication: concurrent calls share a single request, can be refreshed after completion). */
async function initConfig() {
  if (configPromise) return configPromise
  configPromise = (async () => {
    try {
      config.value = await api.getConfig()
    } catch (e) {
      console.error('initConfig', e)
    }
  })().finally(() => { configPromise = null })
  return configPromise
}

/** 强制刷新配置（设置页保存后调用，让 tts_available / 当前 profile 等即时更新）。Force refresh config (called after saving settings page, to immediately update tts_available / current profile etc.). */
async function refreshConfig() {
  config.value = null
  return initConfig()
}

/** 配置管理 composable（读取 /api/config）。Config management composable (reads /api/config). */
export function useConfig() {
  return { config, initConfig, refreshConfig }
}
