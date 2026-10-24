/**
 * API Token 鉴权 —— 服务端在配置了 server.api_token 时，所有 /api/* 请求
 * （含 WebSocket）都要求携带 token。本地默认不配置，因此无 token 时行为不变。
 *
 * API token auth — when server.api_token is configured, every /api/* request
 * (WebSocket included) must carry it. Local defaults leave it empty, so the
 * no-token behaviour is unchanged.
 */

const STORAGE_KEY = 'xluo.apiToken'

/**
 * 读取并消费地址栏里的 ?token= 引导参数（首次打开时写入 localStorage）。
 * Read and consume the ?token= bootstrap parameter from the address bar.
 */
function takeUrlToken(): string {
  try {
    const url = new URL(window.location.href)
    const token = url.searchParams.get('token') || ''
    if (token) {
      url.searchParams.delete('token')
      window.history.replaceState({}, '', url.toString())
    }
    return token
  } catch {
    return ''
  }
}

/** 当前 token（URL 引导 > localStorage > 空）。Current token. */
export function getApiToken(): string {
  const fromUrl = takeUrlToken()
  if (fromUrl) {
    setApiToken(fromUrl)
    return fromUrl
  }
  try {
    return localStorage.getItem(STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

/** 设置/清除 token（空串 = 清除）。Set or clear the token. */
export function setApiToken(token: string): void {
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* localStorage 不可用（隐私模式）时静默降级 */
  }
}

/** 供 fetch 使用的鉴权头（无 token 时为空对象）。Auth headers for fetch. */
export function authHeaders(): Record<string, string> {
  const token = getApiToken()
  return token ? { 'X-API-Token': token } : {}
}

/** 给 WebSocket URL 追加 token 查询参数（服务端同时接受头与查询参数）。Append the token query parameter to a WebSocket URL. */
export function withTokenParam(url: string): string {
  const token = getApiToken()
  if (!token) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}token=${encodeURIComponent(token)}`
}
