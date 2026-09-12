<template>
  <!-- 高级模块：Agent / LLM 客户端 / 工具 / RAG / 服务器参数配置。Advanced module: Agent / LLM client / Tools / RAG / Server settings. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">高级设置（Agent / LLM 客户端 / 工具 / 服务器 / MCP）</span>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule('advanced')">
        {{ s.saving.value ? '保存中…' : '保存' }}
      </UiButton>
    </div>
    <div v-for="d in advancedDefs" :key="d.key" class="cs-subcard">
      <div class="cs-subcard-title">{{ d.title }}</div>
      <template v-for="f in d.fields" :key="f[0]">
        <SettingsField v-if="f[1] === 'bool'" :label="fieldLabel(f[0])" row>
          <UiToggle :model-value="s.sec(d.key)[f[0]]" @update:model-value="v => (s.sec(d.key)[f[0]] = v)" />
        </SettingsField>
        <SettingsField v-else :label="fieldLabel(f[0])">
          <UiInput :type="f[1] === 'number' ? 'number' : 'text'" v-model="s.sec(d.key)[f[0]]" />
        </SettingsField>
      </template>
    </div>
    <p class="cs-note">
      MCP server 列表、服务器 host/port/api_token 建议直接编辑 config.yaml / config.secrets.yaml（改动需重启生效）。
      密钥只报「已设置 / 未设置」，永不回显。
    </p>
  </UiCard>
</template>

<!-- 高级设置卡：字段表由 configDefs.advancedDefs 驱动。Advanced settings card: fields driven by configDefs.advancedDefs. -->
<script setup lang="ts">
import SettingsField from './SettingsField.vue'
import { UiButton, UiCard, UiInput, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { advancedDefs, fieldLabel } from './configDefs'

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}
.cs-subcard {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft); border-radius: var(--r-md);
  background: rgba(15, 23, 42, .4);
}
.cs-subcard-title {
  font-size: var(--fs-xs); font-weight: 600; color: var(--text-2);
  letter-spacing: .02em;
}
.cs-note {
  font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6;
  margin: 4px 0 0;
}
</style>
