import { ref } from 'vue'
import { api } from '../../../api'
import { notify } from '../../../composables/useToast'
import { formatError } from '../../../errors'
import { editable } from './state'

/**
 * API Key 弹窗与密钥读写（永不回显，只报已设置 / 未设置）。
 * API Key modal and secret read/write (never echoed back; only reports set / unset).
 */

/** 密钥弹出框状态（section / profile / value）。API Key modal state. */
export const keyModal = ref<{ section: string; profile: string; value: string } | null>(null)
/** 是否显示明文密钥。Whether to show the key in plain text. */
export const showKey = ref(false)

/**
 * 打开密钥设置弹窗。
 * Open the API Key settings modal.
 *
 * @param section 模块 key。Module key.
 * @param profile Profile 名。Profile name.
 */
export function openKeyModal(section: string, profile: string) {
  showKey.value = false
  keyModal.value = { section, profile, value: '' }
}

/**
 * 获取当前密钥对应的环境变量名（提示用户可通过 env 配置）。
 * Get the env var name for the current key (hints that env config is available).
 *
 * @returns 环境变量名，无则空串。The env var name, or an empty string.
 */
export function keyEnvHint(): string {
  const m = keyModal.value
  if (!m) return ''
  return (editable.value as any)?.[m.section]?.profiles?.[m.profile]?.api_key_env || ''
}

/**
 * 确认保存 API Key（通过 PUT secret 接口）。
 * Confirm and save the API Key (via the PUT secret endpoint).
 */
export async function confirmKey() {
  const m = keyModal.value
  if (!m) return
  const path = `${m.section}.profiles.${m.profile}`
  const label = `${m.section} · ${m.profile}`
  try {
    const r = await api.putSecret(path, m.value)
    if (r.ok) {
      if (r.set) notify.ok(`已设置 ${label} 密钥（即时生效）`)
      else notify.ok(`已清除 ${label} 密钥`)
      const s = (editable.value as any)?.[m.section]
      if (s?.api_key_set) s.api_key_set[m.profile] = r.set
      keyModal.value = null
    } else {
      notify.err('设置密钥失败：' + (r.error || ''))
    }
  } catch (e) {
    notify.err('设置密钥失败：' + formatError(e))
  }
}

/**
 * 清除当前 API Key（value 置空后调用 confirmKey）。
 * Clear the current API Key (empties the value, then calls confirmKey).
 */
export async function clearKey() {
  const m = keyModal.value
  if (!m) return
  m.value = ''
  await confirmKey()
}
