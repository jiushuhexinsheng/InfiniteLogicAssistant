<template>
  <!-- 服务模块卡：LLM / ASR / TTS 共用（字段表由 sectionDefs 驱动）。Service module card: shared by LLM / ASR / TTS, fields driven by sectionDefs. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">{{ section.title }}</span>
      <div class="cs-card-btns">
        <!-- 测试连接：进行中显示旋转动画 +「测试中…」（按钮禁用防重复点）；结果走 toast。
             Test connection: spinning animation + "testing…" while running (disabled to
             prevent double clicks); results go through a toast. -->
        <UiButton variant="secondary" size="sm" :disabled="s.detecting.value" @click="s.detectOne(section.name)">
          <UiIcon v-if="s.detecting.value" name="loader-2" :size="12" class="cs-spin" />
          {{ s.detecting.value ? '测试中…' : '测试连接' }}
        </UiButton>
        <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="s.saveModule(section.key)">
          {{ s.saving.value ? '保存中…' : '保存' }}
        </UiButton>
      </div>
    </div>

    <!-- 卡体：唯一滚动面（卡头含保存/测试连接固定在其上方）。
         The card body: the only scrolling surface (the head — 保存/测试连接 — stays fixed above). -->
    <div class="cs-card-body">

    <SettingsField v-if="section.toggle" label="启用" row>
      <UiToggle :model-value="s.sec(section.key).enabled" @update:model-value="v => (s.sec(section.key).enabled = v)" />
    </SettingsField>

    <!-- Profile 管理：切换 / 新增（自填） / 删除。Profile management: switch / add (self-filled) / delete. -->
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
        <!-- 音频格式下拉：后端 TtsProfile.format 是 wav/mp3/pcm16 三值字面量，文本框能输非法值。
             Audio format dropdown: backend TtsProfile.format is a wav/mp3/pcm16 literal; a free-text box accepts invalid values. -->
        <UiSelect v-else-if="f === 'format'" :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)">
          <option value="wav">wav</option>
          <option value="mp3">mp3</option>
          <option value="pcm16">pcm16</option>
        </UiSelect>
        <!-- 模型 / 音色可输入下拉：支持手动输入或从列表选择。Model / voice input with datalist: manual input or pick from the list. -->
        <template v-else-if="f === 'model' || f === 'voice'">
          <UiInput :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)" :list="`dl-${section.key}-${f}`" />
          <datalist :id="`dl-${section.key}-${f}`">
            <option v-for="m in (f === 'model' ? s.modelOptions(section) : s.voiceOptions(section))" :key="m" :value="m" />
          </datalist>
        </template>
        <!-- 音色列表编辑器：写回 profile.voices，同时喂给上面「音色」输入框的 datalist。
             Voice list editor: writes back profile.voices, which also feeds the datalist of the "voice" input above. -->
        <template v-else-if="f === 'voices'">
          <div v-for="(_, i) in (s.sec(section.key).profiles[s.sec(section.key).active].voices || [])" :key="i" class="cs-voicerow">
            <UiInput :model-value="s.sec(section.key).profiles[s.sec(section.key).active].voices[i]" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active].voices[i] = v)" placeholder="如 alloy" />
            <UiButton variant="secondary" size="sm" hover="danger" @click="s.sec(section.key).profiles[s.sec(section.key).active].voices.splice(i, 1)">删除</UiButton>
          </div>
          <UiButton variant="secondary" size="sm" @click="addVoice">＋ 新增音色</UiButton>
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

    <!-- 高级兼容（自填闭环）：特殊网关的请求体补丁，厂商预设退役后在此编辑。
         Advanced gateway compat: request-body patches for special gateways; edited here
         after the vendor presets retired. -->
    <div class="cs-compat">
      <div class="cs-compat-head">
        <span class="cs-compat-title">高级兼容</span>
        <span class="cs-compat-hint">特殊网关的请求体补丁（如小米需 auth_header/audio_data_url）</span>
      </div>
      <div class="cs-compat-shortcuts">
        <button
          v-for="c in s.compatShortcuts" :key="c.key" type="button"
          class="cs-compat-chip" :class="{ on: compatHas(c.key) }"
          @click="s.toggleCompat(section, c.key, c.value)"
        >{{ c.label }}</button>
      </div>
      <div v-for="(row, i) in s.compatEntries(section)" :key="i" class="cs-compat-row">
        <UiInput :model-value="row[0]" @update:model-value="v => renameCompat(i, row[0], v)" placeholder="键" />
        <UiInput :model-value="row[1]" @update:model-value="v => s.setCompat(section, row[0], v, row[0])" placeholder="值" />
        <UiButton variant="secondary" size="sm" hover="danger" @click="s.removeCompat(section, row[0])">删除</UiButton>
      </div>
      <UiButton variant="secondary" size="sm" @click="addCompat">＋ 新增兼容键</UiButton>
    </div>

    <!-- 扩展插槽：TTS 卡在此挂载播报设置面板（引擎 / 音色 / 音量 / 试听）。
         Extension slot: the TTS card mounts the playback settings panel here (engine / voice / volume / preview). -->
    <slot />
    </div><!-- /cs-card-body -->
  </UiCard>
</template>

<script setup lang="ts">
import SettingsField from './SettingsField.vue'
import VendorPicker from './VendorPicker.vue'
import { UiButton, UiCard, UiChip, UiIcon, UiInput, UiSelect, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { fieldLabel, isNumericField, type SectionDef } from './configDefs'

/** 组件 props：服务模块定义（来自 configDefs.sectionDefs）。Component props: the service module definition (from configDefs.sectionDefs). */
const props = defineProps<{ section: SectionDef }>()

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/** 当前活跃 Profile（voices 列表编辑用）。The active profile (for editing the voices list). */
function activeProfile(): any {
  const sec = s.sec(props.section.key)
  return sec?.profiles?.[sec.active]
}

/** 向 profile.voices 追加一个空音色行（列表不存在时先初始化）。
 *  Append an empty voice row to profile.voices (initializing the list if missing). */
function addVoice() {
  const prof = activeProfile()
  if (!prof) return
  if (!Array.isArray(prof.voices)) prof.voices = []
  prof.voices.push('')
}

// ─── 高级兼容编辑辅助（数据直改 editable 快照，随「保存」一并 PATCH） ───

/** 当前 profile 是否已有某兼容键。Whether the active profile has a compat key. */
function compatHas(key: string): boolean {
  return s.compatEntries(props.section).some(([k]) => k === key)
}

/** 追加一个空兼容键行（占位键名，改名即生效）。Append an empty compat row. */
function addCompat() {
  s.setCompat(props.section, `key_${Date.now().toString(36)}`, '')
}

/** 重命名兼容键（本质 = 删旧建新，值不变）。Rename a compat key (delete + recreate, value kept). */
function renameCompat(_i: number, oldKey: string, newKey: string) {
  const cur = s.compatEntries(props.section).find(([k]) => k === oldKey)
  s.setCompat(props.section, newKey, cur?.[1] ?? '', oldKey)
}
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
/* 音色列表行：一行一个音色 + 删除按钮（与唤醒词行同构）。Voice row: one voice plus a delete button (mirrors the wake-word row). */
.cs-voicerow { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cs-voicerow :deep(.ui-input) { flex: 1; min-width: 0; }

/* 高级兼容编辑区：折叠密度 + 快捷 chip（与音色行同构的键值行）。Advanced compat editor:
   compact density + shortcut chips (key-value rows mirroring the voice row). */
.cs-compat { border-top: 1px dashed var(--border-soft); padding-top: 9px; display: flex; flex-direction: column; gap: 7px; }
.cs-compat-head { display: flex; align-items: baseline; gap: 8px; }
.cs-compat-title { font-size: var(--fs-2xs); font-weight: 600; color: var(--text-2); letter-spacing: .04em; }
.cs-compat-hint { font-size: var(--fs-2xs); color: var(--text-3); }
.cs-compat-shortcuts { display: flex; flex-wrap: wrap; gap: 6px; }
.cs-compat-chip {
  font-size: var(--fs-2xs); font-family: var(--font-mono); color: var(--text-3);
  background: rgba(15, 23, 42, .6); border: 1px solid var(--border-soft);
  border-radius: var(--r-full); padding: 2px 9px; cursor: pointer;
}
.cs-compat-chip:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.cs-compat-chip.on { color: var(--brand-c2); border-color: var(--brand-c2); background: rgba(52, 211, 153, .08); }
.cs-compat-row { display: flex; align-items: center; gap: 8px; }
.cs-compat-row :deep(.ui-input) { flex: 1; min-width: 0; font-family: var(--font-mono); }

/* 测试中旋转动画（挂在 loader-2 图标上）。Spin animation while a connection test runs
   (applied to the loader-2 icon). */
.cs-spin { animation: cs-spin .9s linear infinite; }
@keyframes cs-spin { to { transform: rotate(360deg); } }
</style>
