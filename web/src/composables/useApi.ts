import { ref } from 'vue'
import { api } from '../api'
import type { ConfigResponse } from '../types'

/**
 * 配置管理 composable（读取 /api/config）
 */
export function useConfig() {
  const config = ref<ConfigResponse | null>(null)

  async function initConfig() {
    try {
      config.value = await api.getConfig()
    } catch (e) {
      console.error('initConfig', e)
    }
  }

  return { config, initConfig }
}
