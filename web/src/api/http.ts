// ─── HTTP 封装 / HTTP Wrappers ───

/** API 基础路径 */
/** API base path */
export const BASE = '/api'

/**
 * 通用 HTTP 请求函数，处理响应和错误
 * Generic HTTP request function that handles responses and errors
 * @param path - API 路径 / API path
 * @param options - fetch 请求选项 / fetch request options
 * @returns Promise<T> - 解析后的 JSON 响应 / Parsed JSON response
 */
export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    // 尝试解析 JSON 错误体，失败则用 HTTP 状态码
    // Try to parse JSON error body, fallback to HTTP status code
    let message = `HTTP ${res.status}`
    try {
      const err = await res.json()
      if (err?.error) message = err.error
    } catch { /* not JSON */ }
    throw new Error(message)
  }
  const data = await res.json()
  return data as T
}

/** GET 请求封装。GET request wrapper. */
export async function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

/** POST 请求封装。POST request wrapper. */
export async function post<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

/** PATCH 请求封装。PATCH request wrapper. */
export async function patchHttp<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

/** PUT 请求封装。PUT request wrapper. */
export async function putHttp<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

/** DELETE 请求封装。DELETE request wrapper. */
export async function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}
