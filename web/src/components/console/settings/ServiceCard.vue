<template>
  <!-- 服务模块卡：LLM / ASR / TTS 共用（字段表由 sectionDefs 驱动）。Service module card: shared by LLM / ASR / TTS, fields driven by sectionDefs. -->
  <SettingsCard :title="section.title">
    <template #actions>
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
    </template>

    <!-- 卡体内容；卡头（含保存/测试连接）由 SettingsCard 固定在其上方。
         Body content; the head (保存/测试连接) is held fixed above by SettingsCard. -->
    <SettingsField v-if="section.toggle" label="启用" row>
      <UiToggle :model-value="s.sec(section.key).enabled" @update:model-value="v => (s.sec(section.key).enabled = v)" />
    </SettingsField>

    <!-- 段级三选一（ASR 转写模式：本地/云端/混合）。随「保存」一并 PATCH。
         Section-level segmented control (ASR transcription mode); saved with the rest. -->
    <SettingsField v-if="section.modeField" :label="fieldLabel(section.modeField.key)">
      <UiSegmented
        :model-value="s.sec(section.key)[section.modeField.key]"
        :options="section.modeField.options"
        :aria-label="fieldLabel(section.modeField.key)"
        @update:model-value="setModeField"
      />
      <p v-if="section.key === 'asr'" class="cs-mode-hint">{{ asrModeHint }}</p>
      <!-- 本地模型未就位 + 选了需要它的模式 → 明确警示（不是静默失败）。
           Local model missing while a mode that needs it is selected → a clear warning. -->
      <p v-if="section.key === 'asr' && !s.sec('asr').local_model_present && s.sec('asr').mode !== 'cloud'" class="cs-note">
        ⚠️ 本地 ASR 模型未就位：运行 <code>python scripts/fetch_local_asr_model.py</code> 下载，
        或把「转写模式」改回云端。<template v-if="s.sec('asr').mode === 'local'">本地模式下语音转写会明确报错，且音频<strong>不会</strong>上云。</template>
      </p>
    </SettingsField>

    <!-- Profile 管理：切换 / 新增（自填） / 删除。Profile management: switch / add (self-filled) / delete. -->
    <div class="cs-profrow">
      <SettingsField label="Profile" grow>
        <UiSelect :model-value="s.sec(section.key).active" :options="profileOptions" @update:model-value="v => (s.sec(section.key).active = v)" />
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
        <UiSelect v-if="f === 'provider'" :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" :options="PROVIDERS" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)" />
        <!-- 音频格式下拉：后端 TtsProfile.format 是 wav/mp3/pcm16 三值字面量，文本框能输非法值。
             Audio format dropdown: backend TtsProfile.format is a wav/mp3/pcm16 literal; a free-text box accepts invalid values. -->
        <UiSelect v-else-if="f === 'format'" :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" :options="FORMATS" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)" />
        <!-- 模型 / 音色：UiCombobox（可手输 + 项目风格建议层；替换原生 datalist 弹层）。
             Model / voice: UiCombobox (free typing + project-styled suggestions; replaces
             the native datalist popup). -->
        <template v-else-if="f === 'model' || f === 'voice'">
          <UiCombobox :model-value="s.sec(section.key).profiles[s.sec(section.key).active][f]" @update:model-value="v => (s.sec(section.key).profiles[s.sec(section.key).active][f] = v)" :options="f === 'model' ? s.modelOptions(section) : s.voiceOptions(section)" />
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
        <UiButton
          v-for="c in s.compatShortcuts" :key="c.key"
          size="sm" shape="pill" class="cs-compat-chip" :class="{ on: compatHas(c.key) }"
          @click="s.toggleCompat(section, c.key, c.value)"
        >{{ c.label }}</UiButton>
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
  </SettingsCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import SettingsField from './SettingsField.vue'
import VendorPicker from './VendorPicker.vue'
import SettingsCard from './SettingsCard.vue'
import { UiButton, UiChip, UiCombobox, UiIcon, UiInput, UiSegmented, UiSelect, UiToggle } from '../../ui'
import type { SegOption } from '../../ui/UiSegmented.vue'
import { useSettings } from './useSettings'
import { fieldLabel, isNumericField, type SectionDef } from './configDefs'

/** 组件 props：服务模块定义（来自 configDefs.sectionDefs）。Component props: the service module definition (from configDefs.sectionDefs). */
const props = defineProps<{ section: SectionDef }>()

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/** 协议下拉选项（后端 provider 字面量的单一来源）。Provider options (single source for the backend's provider literals). */
const PROVIDERS: SegOption[] = [
  { value: 'openai', label: 'OpenAI 兼容' },
  { value: 'anthropic', label: 'Anthropic（原生）' },
  { value: 'gemini', label: 'Gemini（原生）' },
]

/** 音频格式下拉选项（后端 TtsProfile.format 是 wav/mp3/pcm16 三值字面量，文本框能输非法值）。
 *  Audio format options (backend TtsProfile.format is a wav/mp3/pcm16 literal; a free-text box would accept invalid values). */
const FORMATS: SegOption[] = [
  { value: 'wav', label: 'wav' },
  { value: 'mp3', label: 'mp3' },
  { value: 'pcm16', label: 'pcm16' },
]

/** Profile 下拉选项：当前 section 已配置的 profile 名。Profile options: the section's configured profile names. */
const profileOptions = computed<SegOption[]>(() =>
  Object.keys(s.sec(props.section.key).profiles).map(n => ({ value: n, label: n })),
)

/** ASR 转写模式说明（仅 ASR 卡用）。ASR transcription-mode hint (ASR card only). */
const asrModeHint = computed(() => {
  switch (s.sec('asr')?.mode) {
    case 'local': return '🔒 本地模式：sherpa-onnx 在本机转写，音频不出本机、零成本（缺模型时明确报错，绝不上云）'
    case 'hybrid': return '🔄 混合模式：本地优先，本地不可用/转写为空时才回落云端（回落会上传，审计记 fallback=1）'
    default: return '☁️ 云端模式：音频上传到当前 ASR profile 的服务商（默认，与旧行为一致）'
  }
})

/** 写入段级 modeField（走函数而非模板内联回调 —— 内联箭头里 `section.modeField`
 *  的 `v-if` 可选链收窄会失效，vue-tsc 报 possibly undefined）。
 *  Write the section-level modeField through a function: inside an inline arrow the
 *  `v-if` narrowing of `section.modeField` does not survive, so vue-tsc complains it may
 *  be undefined. */
function setModeField(v: string | number) {
  const mf = props.section.modeField
  if (mf) s.sec(props.section.key)[mf.key] = String(v)
}

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
/* 双类选择器压过 UiButton 基础样式（同 VendorPicker chip 的特异性手法）。
   Double-class selector outspecifies UiButton base styles (same trick as the VendorPicker chip). */
.cs-compat-shortcuts .cs-compat-chip.ui-btn {
  font-size: var(--fs-2xs); font-family: var(--font-mono); color: var(--text-3);
  background: rgba(15, 23, 42, .6); border: 1px solid var(--border-soft);
  border-radius: var(--r-full); padding: 3px 10px; cursor: pointer;
}
.cs-compat-shortcuts .cs-compat-chip.ui-btn:hover { color: var(--brand-c2); border-color: var(--brand-c2); }
.cs-compat-shortcuts .cs-compat-chip.ui-btn.on { color: var(--brand-c2); border-color: var(--brand-c2); background: rgba(52, 211, 153, .08); }
.cs-compat-row { display: flex; align-items: center; gap: 8px; }
.cs-compat-row :deep(.ui-input) { flex: 1; min-width: 0; font-family: var(--font-mono); }

/* 段级三选一的说明与警示（与 VoiceCard 同款尺寸；scoped 样式不跨组件，故各自定义）。
   Hint / warning for the section-level segmented control (same density as VoiceCard;
   scoped styles do not cross components, so each card defines its own). */
.cs-mode-hint { font-size: var(--fs-2xs); color: var(--text-3); margin: 6px 0 0; line-height: 1.5; }
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 4px 0 0; }
.cs-note strong { color: var(--text-2); }
.cs-note code {
  font-family: var(--font-mono); font-size: inherit;
  background: rgba(148, 163, 184, .12); border-radius: 3px; padding: 0 3px;
}

/* 测试中旋转动画（挂在 loader-2 图标上）。Spin animation while a connection test runs
   (applied to the loader-2 icon). */
.cs-spin { animation: cs-spin .9s linear infinite; }
@keyframes cs-spin { to { transform: rotate(360deg); } }
</style>
