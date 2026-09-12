<template>
  <!-- 服务模块卡：LLM / ASR / TTS 共用（字段表由 sectionDefs 驱动）。Service module card: shared by LLM / ASR / TTS, fields driven by sectionDefs. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">{{ section.title }}</span>
      <div class="cs-card-btns">
        <UiButton variant="secondary" size="sm" :disabled="s.detecting.value" @click="s.detectOne(section.name)">测试连接</UiButton>
        <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule(section.key)">
          {{ s.saving.value ? '保存中…' : '保存' }}
        </UiButton>
      </div>
    </div>

    <SettingsField v-if="section.toggle" label="启用" row>
      <UiToggle :model-value="s.sec(section.key).enabled" @update:model-value="v => (s.sec(section.key).enabled = v)" />
    </SettingsField>

    <!-- Profile 管理：切换 / 新增（厂商目录） / 删除。Profile management: switch / add from vendor catalog / delete. -->
    <div class="cs-profrow">
      <SettingsField label="Profile" grow>
        <UiSelect :model-value="s.sec(section.key).active" @update:model-value="v => (s.sec(section.key).active = v)">
          <option v-for="n in Object.keys(s.sec(section.key).profiles)" :key="n" :value="n">{{ n }}</option>
        </UiSelect>
      </SettingsField>
      <UiButton variant="secondary" size="sm" :class="{ on: s.addingSection.value === section.key }" @click="s.toggleAdding(section.key)">
        <UiIcon name="plus" :size="12" /> 新增
      </UiButton>
      <UiButton variant="secondary" size="sm" :disabled="Object.keys(s.sec(section.key).profiles).length <= 1" @click="s.deleteProfile(section.key)">
        <UiIcon name="trash" :size="12" /> 删除
      </UiButton>
    </div>

    <VendorPicker v-if="s.addingSection.value === section.key" :section-key="section.key" />

    <template v-for="f in section.fields" :key="f">
      <SettingsField :label="fieldLabel(f)">
        <!-- 协议下拉：选择 OpenAI 兼容 / Anthropic / Gemini。Protocol dropdown: choose OpenAI compatible / Anthropic / Gemini. -->
        <UiSelect v-if="f === 'provider'" :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)">
          <option value="openai">OpenAI 兼容</option>
          <option value="anthropic">Anthropic（原生）</option>
          <option value="gemini">Gemini（原生）</option>
        </UiSelect>
        <!-- 模型 / 音色可输入下拉：支持手动输入或从列表选择。Model / voice input with datalist: manual input or pick from the list. -->
        <template v-else-if="f === 'model' || f === 'voice'">
          <UiInput :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)" :list="`dl-${section.key}-${f}`" />
          <datalist :id="`dl-${section.key}-${f}`">
            <option v-for="m in (f === 'model' ? s.modelOptions(section) : s.voiceOptions(section))" :key="m" :value="m" />
          </datalist>
        </template>
        <UiInput
          v-else
          :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]"
          @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)"
          :type="isNumericField(f) ? 'number' : 'text'"
          :step="isNumericField(f) ? (f === 'temperature' ? 0.1 : 1) : undefined"
        />
      </SettingsField>
    </template>

    <div class="cs-keyrow">
      <UiChip :tone="s.sec(section.key).api_key_set[s.sec(section.key).active] ? 'ok' : 'warn'" :dot="false">
        API Key：{{ s.sec(section.key).api_key_set[s.sec(section.key).active] ? '已设置' : '未设置' }}
      </UiChip>
      <UiButton variant="secondary" size="sm" @click="s.openKeyModal(section.key, s.sec(section.key).active)">设置</UiButton>
      <UiButton variant="secondary" size="sm" @click="s.fetchModelsFor(section)">获取模型</UiButton>
    </div>

    <div v-if="s.connResults.value[section.name]" class="cs-connline" :class="'st-' + s.connResults.value[section.name].status">
      {{ s.connResults.value[section.name].detail || s.connResults.value[section.name].status }}
      <em v-if="s.connResults.value[section.name].latency_ms != null">{{ s.connResults.value[section.name].latency_ms }}ms</em>
    </div>
  </UiCard>
</template>

<script setup lang="ts">
import SettingsField from './SettingsField.vue'
import VendorPicker from './VendorPicker.vue'
import { UiButton, UiCard, UiChip, UiIcon, UiInput, UiSelect, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { fieldLabel, isNumericField, type SectionDef } from './configDefs'

/** 组件 props：服务模块定义（来自 configDefs.sectionDefs）。Component props: the service module definition (from configDefs.sectionDefs). */
defineProps<{ section: SectionDef }>()

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
.cs-card-btns { display: flex; align-items: center; gap: 8px; }
.cs-profrow { display: flex; align-items: flex-end; gap: 8px; }
/* 新增 Profile 按钮激活态（UiButton 透传 class）。Active state of the "add Profile" button (class passed through UiButton). */
.cs-profrow :deep(.ui-btn.on) { color: var(--brand-c2); border-color: var(--brand-c2); }
.cs-keyrow { display: flex; align-items: center; gap: 8px; }
.cs-connline {
  font-size: var(--fs-2xs); color: var(--text-3);
  border-top: 1px dashed var(--border-soft); padding-top: 7px;
}
.cs-connline em { font-style: normal; font-family: var(--font-mono); color: var(--brand-c2); margin-left: 6px; }
.st-ok { color: #34d399 !important; border-color: rgba(52, 211, 153, .4) !important; background: rgba(52, 211, 153, .07); }
.st-skip { color: var(--text-3) !important; }
.st-fail { color: #f87171 !important; border-color: rgba(248, 113, 113, .4) !important; background: rgba(248, 113, 113, .07); }
</style>
