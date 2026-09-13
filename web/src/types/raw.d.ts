/**
 * Vite 的 `?raw` 导入声明：把文件内容作为字符串引入。
 *
 * Vite 原生支持，但 `tsconfig` 未包含 `vite/client` 类型，故在此补声明。
 * 用途：测试需要读取 `public/` 下的静态脚本（如唤醒引擎 wake-word.js，它是
 * IIFE 全局变量而非模块）的源码。
 *
 * Ambient declaration for Vite's `?raw` import, which brings a file's contents in as a
 * string. Vite supports it natively, but the tsconfig does not include `vite/client` types,
 * hence this declaration. Used by tests that need the source of a static script under
 * `public/` (e.g. the wake engine wake-word.js, an IIFE global rather than a module).
 */
declare module '*?raw' {
  const source: string
  export default source
}
