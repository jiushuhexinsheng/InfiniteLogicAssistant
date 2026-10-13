/**
 * Vite 客户端类型（`import.meta.env`、资源导入等）。
 *
 * 原先项目里缺这个文件，所以 `import.meta.env` 在 `vue-tsc` 下是「不存在」的 —— 加 dev 期
 * 告警时撞上了（UiIcon 的未注册图标名警告）。
 * Vite client types (`import.meta.env`, asset imports, …).
 *
 * The project was missing this file, so `import.meta.env` did not exist as far as `vue-tsc` was
 * concerned — which surfaced when adding the dev-only warning in UiIcon.
 */
/// <reference types="vite/client" />
