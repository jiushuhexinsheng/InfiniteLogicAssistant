import * as state from './state'
import * as profiles from './profiles'
import * as detection from './detection'
import * as apiKeys from './apiKeys'

/**
 * 设置页状态与操作入口（模块级单例，聚合四个职责域）。
 * Settings-page state and operations entry point (module-level singleton,
 * aggregating four responsibility areas).
 *
 * 实现按职责拆分：
 * - state.ts      核心状态与配置读写（editable / saveModule / load / sec / ed）
 * - profiles.ts   厂商目录与 Profile 管理
 * - detection.ts  连通性检测与配置校验问题
 * - apiKeys.ts    API Key 弹窗与密钥读写
 *
 * 本文件只做聚合，保持 useSettings() 的返回形状不变，使 6 个子组件无需改动。
 * 公开成员由 __tests__/useSettings.spec.ts 锁定，增删成员会立刻反映到该测试。
 *
 * The implementation is split by responsibility (see above). This file only
 * composes them, keeping useSettings()'s shape stable so the six sub-components
 * need no changes. The public members are locked by __tests__/useSettings.spec.ts,
 * so adding or dropping one shows up there immediately.
 *
 * 状态定义在模块顶层（与 useConsole.ts、assistant/store.ts 同模式），各子组件
 * 无需逐层传 props。副作用：state 跨 ConsoleSettings 挂载/卸载存活，故
 * ConsoleSettings 必须保留 onMounted 时重新 load()。
 *
 * State lives at module top level (same pattern as useConsole.ts and
 * assistant/store.ts), so sub-components need no prop drilling. Side effect: state
 * survives ConsoleSettings mount/unmount, so ConsoleSettings MUST keep its
 * onMounted re-load().
 *
 * @returns 状态引用与操作函数。State refs and operation functions.
 */
export function useSettings() {
  return {
    // ── 核心状态与配置读写 / Core state and config load-save ──
    editable: state.editable,
    saving: state.saving,
    activeMenu: state.activeMenu,
    sec: state.sec,
    ed: state.ed,
    menuDot: state.menuDot,
    load: state.load,
    saveModule: state.saveModule,

    // ── 厂商目录与 Profile / Vendor catalog and profiles ──
    catalog: profiles.catalog,
    addingSection: profiles.addingSection,
    customAdding: profiles.customAdding,
    customName: profiles.customName,
    activeProfile: profiles.activeProfile,
    vendorPreset: profiles.vendorPreset,
    vendorList: profiles.vendorList,
    modelOptions: profiles.modelOptions,
    voiceOptions: profiles.voiceOptions,
    presetToProfile: profiles.presetToProfile,
    toggleAdding: profiles.toggleAdding,
    confirmCustom: profiles.confirmCustom,
    addProfileFromVendor: profiles.addProfileFromVendor,
    deleteProfile: profiles.deleteProfile,
    fetchModelsFor: profiles.fetchModelsFor,
    loadCatalog: profiles.loadCatalog,

    // ── 连通性检测 / Connectivity detection ──
    detecting: detection.detecting,
    connResults: detection.connResults,
    issues: detection.issues,
    detectAll: detection.detectAll,
    detectOne: detection.detectOne,

    // ── API Key / API keys ──
    keyModal: apiKeys.keyModal,
    showKey: apiKeys.showKey,
    openKeyModal: apiKeys.openKeyModal,
    keyEnvHint: apiKeys.keyEnvHint,
    confirmKey: apiKeys.confirmKey,
    clearKey: apiKeys.clearKey,
  }
}
