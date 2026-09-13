<template>
  <!-- 权限设置卡：按风险层级设默认动作 + 单工具/通配规则覆盖。
       Permission settings card: per-tier default actions plus per-tool / glob rule overrides. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">工具权限</span>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule('permissions')">
        {{ s.saving.value ? '保存中…' : '保存' }}
      </UiButton>
    </div>

    <p class="cs-note">
      求值顺序：未注册工具 → 拒绝；任一 <code>deny</code> 规则短路（不可被后续规则翻案）；
      首条匹配规则；层级默认；最后 <code>default_action</code>。
    </p>

    <SettingsField label="默认动作（未命中任何规则时）">
      <UiSelect v-model="perms.default_action">
        <option v-for="a in ACTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
      </UiSelect>
    </SettingsField>

    <div class="cs-subcard">
      <div class="cs-subcard-title">按风险层级的默认动作</div>
      <SettingsField v-for="t in TIERS" :key="t.key" :label="t.label">
        <UiSelect v-model="perms.tiers[t.key]">
          <option v-for="a in ACTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
        </UiSelect>
      </SettingsField>
      <p class="cs-note">
        把 <code>exec</code> 设为「允许」意味着所有执行类工具不再询问 —— 请确认你接受该风险。
      </p>
    </div>

    <div class="cs-subcard">
      <div class="cs-subcard-title">规则（优先级高于层级默认）</div>
      <div v-for="(r, i) in perms.rules" :key="i" class="cs-profrow">
        <SettingsField label="工具名或通配" grow>
          <UiInput v-model="r.match" list="perm-tool-names" placeholder="如 run_* 或 read_file" />
        </SettingsField>
        <SettingsField label="动作">
          <UiSelect v-model="r.action">
            <option v-for="a in ACTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
          </UiSelect>
        </SettingsField>
        <UiButton variant="secondary" size="sm" hover="danger" @click="perms.rules.splice(i, 1)">删除</UiButton>
      </div>
      <datalist id="perm-tool-names">
        <option v-for="n in toolNames" :key="n" :value="n" />
      </datalist>
      <UiButton variant="secondary" size="sm" @click="perms.rules.push({ match: '', action: 'ask' })">＋ 新增规则</UiButton>
    </div>
  </UiCard>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../../../api'
import SettingsField from './SettingsField.vue'
import { UiButton, UiCard, UiInput, UiSelect } from '../../ui'
import { useSettings } from './useSettings'

/** 设置页单例（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/** 可选的权限动作。The available permission actions. */
const ACTIONS = [
  { value: 'allow', label: '允许（不问）' },
  { value: 'ask', label: '询问' },
  { value: 'deny', label: '拒绝' },
]

/** 三个风险层级。The three risk tiers. */
const TIERS = [
  { key: 'read' as const, label: '只读工具' },
  { key: 'write' as const, label: '写入工具' },
  { key: 'exec' as const, label: '执行工具' },
]

/** 已注册工具名（规则 match 输入的 datalist 提示）。Registered tool names (datalist hints for the rule match input). */
const toolNames = ref<string[]>([])

/** 权限段的响应式视图；editable 未加载时给一份安全默认，避免模板空引用（卡片本身有 v-if 守卫）。 */
const perms = computed(() => {
  const p = (s.editable.value as any)?.permissions
  return p ?? { default_action: 'ask', tiers: { read: 'allow', write: 'ask', exec: 'ask' }, rules: [] }
})

onMounted(async () => {
  try {
    const r = await api.getTools()
    if (r.ok) toolNames.value = r.tools.map((t) => t.function.name)
  } catch { /* 工具名仅作输入提示，拉取失败不影响编辑 / tool names are hints only */ }
})
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); letter-spacing: .02em; }
.cs-subcard {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 12px; border: 1px solid var(--border-soft); border-radius: var(--r-md);
  background: rgba(15, 23, 42, .4);
}
.cs-subcard-title { font-size: var(--fs-xs); font-weight: 600; color: var(--text-2); letter-spacing: .02em; }
.cs-profrow { display: flex; align-items: flex-end; gap: 8px; }
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 4px 0 0; }
</style>
