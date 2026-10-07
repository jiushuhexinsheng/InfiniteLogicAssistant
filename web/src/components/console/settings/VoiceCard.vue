<template>
  <!-- 语音模块：唤醒词 + VAD。Voice module: wake word + VAD. -->
  <UiCard class="cs-card">
    <div class="cs-card-head">
      <span class="cs-card-title">语音（唤醒 / 静音检测）</span>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="saveVoice()">
        {{ s.saving.value ? '保存中…' : '保存' }}
      </UiButton>
    </div>
    <!-- 隐私边界：spec 明确要求「必须写进 README 与设置页」。口径对齐 wiki/Security.md：
         云端模式（旁路闸门）无条件上传；自动/本地经后端 KWS 闸门（未命中不上云、命中才
         上传抬指令）；浏览器模式走浏览器识别（并不更私密）。旧文案「云端/自动都上传」
         「本地/浏览器音频不出本机」与 KWS 闸门后的实现相反，已按 P3-8 删除。
         Privacy boundary (spec-required). Aligned with wiki/Security.md: cloud mode bypasses
         the gate and uploads unconditionally; auto/local go through the backend KWS gate
         (misses stay local, hits upload for instruction extraction); browser mode uses the
         browser's recognizer (not more private). The old copy ("cloud/auto both upload",
         "local/browser audio never leaves") contradicted the post-gate implementation. -->
    <p class="cs-note">
      ⚠️ <strong>云端模式</strong>下，每次 VAD 判到人声都会上传音频到云端 ASR —— <strong>无论是否说出唤醒词</strong>。
      <strong>自动/本地模式</strong>经后端 KWS 闸门：没说唤醒词的段在本机丢弃、不上云，命中才上传抬取指令文本；
      <strong>浏览器模式</strong>走浏览器识别（Chrome 中文经 Google 服务器，并不更私密）。
      关闭下方「唤醒启用」即停止取麦；不接受音频上传请改用文字输入。
    </p>
    <SettingsField v-if="s.editable.value" label="唤醒启用" row>
      <UiToggle :model-value="s.ed().wake_word.enabled" @update:model-value="v => (s.ed().wake_word.enabled = v)" />
    </SettingsField>
    <!-- 唤醒模式切换：自动/本地 = 后端 KWS 闸门判定；云端 = 旁路闸门纯云端；浏览器 = Web Speech API。
         Auto/local = backend KWS gate; cloud = bypass gate, full cloud; browser = Web Speech API. -->
    <SettingsField label="唤醒模式">
      <UiSegmented
        :model-value="currentMode"
        :options="modeOptions"
        aria-label="唤醒模式"
        @update:model-value="v => switchMode(v as WakeMode)"
      />
      <p class="cs-mode-hint">{{ modeHint }}</p>
    </SettingsField>
    <!-- 唤醒词是**列表**（命中任意一个即唤醒）：绑定 singular `keyword` 会读到 undefined
         （输入框空白、看起来「没配」），保存时又被 `keywords` 盖掉 —— 界面等于改不动唤醒词。
         增删行的做法与「权限」卡的规则列表一致。
         The wake word is a **list** (any hit wakes): binding the singular `keyword` reads
         undefined (a blank box that looks unconfigured) and on save `keywords` wins, so the wake
         word could not be changed from the UI at all. Add/remove rows follow the permissions card's
         rule list. -->
    <SettingsField v-if="s.editable.value" label="唤醒词（可多个，说哪个都能唤醒）">
      <div v-for="(_, i) in (s.ed().wake_word.keywords || [])" :key="i" class="cs-kwrow">
        <UiInput v-model="s.ed().wake_word.keywords[i]" placeholder="如 衍衡" />
        <UiButton
          variant="secondary" size="sm" hover="danger"
          :disabled="(s.ed().wake_word.keywords || []).length <= 1"
          @click="s.ed().wake_word.keywords.splice(i, 1)"
        >删除</UiButton>
      </div>
      <UiButton variant="secondary" size="sm" @click="s.ed().wake_word.keywords.push('')">＋ 新增唤醒词</UiButton>
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="灵敏度（0-1）">
      <UiInput type="number" step="0.05" min="0" max="1" :model-value="s.ed().wake_word.sensitivity" @update:model-value="v => (s.ed().wake_word.sensitivity = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="静音判定阈值">
      <UiInput type="number" step="0.01" :model-value="s.ed().vad.silence_threshold" @update:model-value="v => (s.ed().vad.silence_threshold = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="静音停止时长（ms）">
      <UiInput type="number" :model-value="s.ed().vad.silence_duration_ms" @update:model-value="v => (s.ed().vad.silence_duration_ms = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="最长录音（ms）">
      <UiInput type="number" :model-value="s.ed().vad.max_duration_ms" @update:model-value="v => (s.ed().vad.max_duration_ms = toNum(v))" />
    </SettingsField>
    <!-- 成本控制的两个旋钮：wiki/Configuration.md 与 config.yaml.example 都把它们当作「降调用量」
         的手段介绍，设置页却改不了，只能手改配置文件 —— 同族的其余 vad 参数这里都能调。
         The two cost knobs: Configuration.md and config.yaml.example both present them as the way to
         cut call volume, yet the settings page could not touch them while every sibling vad
         parameter is editable here. -->
    <SettingsField v-if="s.editable.value" label="最短语音时长（ms，短于此不上传）">
      <UiInput type="number" min="0" :model-value="s.ed().vad.min_speech_ms" @update:model-value="v => (s.ed().vad.min_speech_ms = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="上传节流（ms，两次唤醒判定的最小间隔）">
      <UiInput type="number" min="0" :model-value="s.ed().vad.upload_throttle_ms" @update:model-value="v => (s.ed().vad.upload_throttle_ms = toNum(v))" />
    </SettingsField>
    <SettingsField v-if="s.editable.value" label="唤醒后等指令超时（ms）">
      <UiInput type="number" min="1" :model-value="s.ed().vad.answer_timeout_ms" @update:model-value="v => (s.ed().vad.answer_timeout_ms = toNum(v))" />
    </SettingsField>
    <!-- 打断播报（barge-in，docs/designs/02 批3）：助手说话时也可直接开口打断。
         默认关 = 播报期间停麦的旧行为。 -->
    <SettingsField v-if="s.editable.value" label="打断播报（助手说话时可直接开口打断）" row>
      <UiToggle :model-value="s.ed().vad.barge_in" @update:model-value="v => (s.ed().vad.barge_in = v)" />
    </SettingsField>
    <!-- 续聊窗口（docs/designs/03-A）：回合结束后的免唤醒接话窗口，0=关闭。 -->
    <SettingsField v-if="s.editable.value" label="续聊窗口（ms，结束后免唤醒直接说话；0=关）">
      <UiInput type="number" min="0" :model-value="s.ed().vad.followup_window_ms" @update:model-value="v => (s.ed().vad.followup_window_ms = toNum(v))" />
    </SettingsField>
  </UiCard>
</template>

<!-- 语音模块卡：唤醒词 / VAD 参数。Voice module card: wake word / VAD params. -->
<script setup lang="ts">
import { computed } from 'vue'
import SettingsField from './SettingsField.vue'
import { UiButton, UiCard, UiInput, UiSegmented, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { notify } from '../../../composables/useToast'
import { wakeMode, setWakeMode, type WakeMode } from '../../../composables/assistant/store'

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/** 唤醒模式选项。Wake mode options. */
const modeOptions: { value: WakeMode; label: string }[] = [
  { value: 'auto', label: '自动' },
  { value: 'local', label: '本地' },
  { value: 'cloud', label: '云端' },
  { value: 'webspeech', label: '浏览器' },
]

/** 当前唤醒模式。Current wake mode. */
const currentMode = computed(() => wakeMode.value)

/** 模式说明文案。Mode description text. */
const modeHint = computed(() => {
  switch (wakeMode.value) {
    case 'local': return '⚡ 本地模式：经后端 KWS 闸门判定（sherpa-onnx 跑在本机后端），未命中不上云、零 LLM 成本'
    case 'cloud': return '☁️ 云端模式：跳过 KWS 闸门直接云端转写判定，延迟较高但识别率高'
    case 'webspeech': return '🌐 浏览器模式：Web Speech API 直接识别，免费但识别率较低'
    default: return '🔄 自动模式：经后端 KWS 闸门判定（未命中不上云），链路失败回退 Web Speech API'
  }
})

/** 切换唤醒模式。Switch the wake mode. */
function switchMode(m: WakeMode) {
  setWakeMode(m)
  notify.ok(`唤醒模式已切换为「${modeOptions.find(o => o.value === m)?.label}」，重新开启唤醒后生效`)
}

/**
 * 数值输入：保留空串（清空），其余转 number（与原生 v-model.number 行为一致）。
 * Numeric input: keep the empty string (cleared), otherwise convert to number
 * (consistent with native v-model.number).
 *
 * @param v 输入框原值。The raw input value.
 * @returns 数值或空串。The number, or an empty string.
 */
function toNum(v: string): number | '' {
  return v === '' ? '' : Number(v)
}

/**
 * 保存语音模块：先剔除空的唤醒词，全空则拒绝保存。
 *
 * 空唤醒词既唤不醒也看不出问题（界面上就是一个空输入框），而空的 keywords 列表意味着
 * **唤醒永远不会命中** —— 一个静默的永久失效，正是本重构要消灭的那一类。要关掉唤醒请用
 * 上面的「唤醒启用」开关（那是一个看得见的意图），别用清空输入框来表达。
 *
 * Save the voice module: drop blank keywords first, and refuse when every keyword is blank.
 * A blank keyword can never wake anything and looks like nothing is wrong (it is just an empty
 * box), and an empty `keywords` list means **the wake word can never match** — a silent permanent
 * failure, exactly the class this rework removes. To turn wake off, use the `唤醒启用` toggle
 * above (a visible intent), not a cleared input.
 */
function saveVoice() {
  const list: unknown = s.ed()?.wake_word?.keywords
  if (!Array.isArray(list)) { void s.saveModule('voice'); return }
  const cleaned = list.map((k) => String(k ?? '').trim()).filter(Boolean)
  if (!cleaned.length) {
    notify.err('唤醒词不能全部为空：清空后唤醒将永远不会命中；要停用请关闭「唤醒启用」')
    return
  }
  s.ed().wake_word.keywords = cleaned
  void s.saveModule('voice')
}
</script>

<style scoped>
.cs-card { display: flex; flex-direction: column; gap: 12px; }
.cs-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cs-card-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-1);
  letter-spacing: .02em;
}
/* 隐私边界说明：与「权限」卡的同名段落保持一致的易读尺寸。
   Privacy note, matching the permissions card's note for readability. */
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 0; }
.cs-note strong { color: var(--text-2); }
.cs-note code {
  font-family: var(--font-mono); font-size: inherit;
  background: rgba(148, 163, 184, .12); border-radius: 3px; padding: 0 3px;
}
/* 唤醒词行：一行一个关键词 + 删除按钮。Wake-keyword row: one keyword plus a delete button. */
.cs-kwrow { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cs-mode-hint { font-size: var(--fs-2xs); color: var(--text-3); margin: 6px 0 0; line-height: 1.5; }
</style>
