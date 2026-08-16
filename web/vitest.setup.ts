// Node 测试环境无 localStorage：提供内存 mock（供 store 持久化测试读取）
const store = new Map<string, string>()

;(globalThis as any).localStorage = {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => { store.set(k, v) },
  removeItem: (k: string) => { store.delete(k) },
  clear: () => store.clear(),
}
;(globalThis as any).__localStore = store
