import { ref } from 'vue'
import { api } from '../api'
import type { ConfigResponse } from '../types'

// 模块级单例配置 —— 全站共享一份 config（悬浮球 / 开始页 / 控制台）
const config = ref<ConfigResponse | null>(null)
let configPromise: Promise<void> | null = null

/** 拉取 /api/config（单飞幂等：并发调用共享一次请求，完成后可再次刷新） */
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

/** 配置管理 composable（读取 /api/config） */
export function useConfig() {
  return { config, initConfig }
}
