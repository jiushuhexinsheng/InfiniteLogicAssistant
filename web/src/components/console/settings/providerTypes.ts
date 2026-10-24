/** 供应商列表摘要（modelCount 由页面按 models ∪ model 计算）。
 *  Provider-list summary (modelCount is computed by the page as models ∪ model). */
export interface ProviderSummary {
  id: string
  name: string
  protocol: string
  endpoint: string
  keySet: boolean
  active: boolean
  modelCount: number
}
