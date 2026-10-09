/**
 * 门面（re-export）：保持原导入路径与导出面不变。
 * Facade: preserves the original import path and export surface.
 */
export type { WakeMatch } from './wakeMatch/detectWake'
export { WAKE_COOLDOWN_MS, enterWakeCooldown, isWakeCooldown, detectWake } from './wakeMatch/detectWake'
