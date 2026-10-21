<template>
  <!-- 语音模块：唤醒词 + VAD。Voice module: wake word + VAD. -->
  <SettingsCard title="唤醒与对话时序" title-en="Wake Word & Timing">
    <template #actions>
      <UiButton variant="primary" size="sm" :disabled="!s.editable.value || s.saving.value" @click="saveVoice()">
        <BiLabel :zh="s.saving.value ? T.saving.zh : T.save.zh"
                 :en="s.saving.value ? T.saving.en : T.save.en" />
      </UiButton>
    </template>

    <!-- 卡体内容；卡头由 SettingsCard 固定在其上方。
         Body content; the card head is held fixed above by SettingsCard. -->
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
      🎙️ <strong>转写模式</strong>（「识别」Tab）＝<strong>{{ asrModeLabel }}</strong>：{{ asrPrivacyLine }}。
    </p>
    <p class="cs-note">
      ⚠️ <strong>转写模式＝云端</strong>时，每个 VAD 判到的人声段都会上传到 ASR 服务商 —— <strong>无论是否说出唤醒词</strong>。
      <strong>本地</strong>模式音频不出本机（VAD/KWS/ASR 都在本机）；<strong>混合</strong>仅在本机失败或转写为空时上传兜底。
      不接受音频上传请把「识别」Tab 切到本地，或改用文字输入。
    </p>
    <SettingsField v-if="s.editable.value" label="唤醒启用" en="Wake enabled" row>
      <UiToggle :model-value="s.ed().wake_word.enabled" @update:model-value="v => (s.ed().wake_word.enabled = v)" />
    </SettingsField>
    <!-- 唤醒词是**列表**（命中任意一个即唤醒）：绑定 singular `keyword` 会读到 undefined
         （输入框空白、看起来「没配」），保存时又被 `keywords` 盖掉 —— 界面等于改不动唤醒词。
         增删行的做法与「权限」卡的规则列表一致。
         The wake word is a **list** (any hit wakes): binding the singular `keyword` reads
         undefined (a blank box that looks unconfigured) and on save `keywords` wins, so the wake
         word could not be changed from the UI at all. Add/remove rows follow the permissions card's
         rule list. -->
    <SettingsField v-if="s.editable.value" label="唤醒词（可多个，说哪个都能唤醒）" en="Wake words">
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
    <SettingsField v-if="s.editable.value" label="灵敏度（0-1）" en="Sensitivity (0-1)">
      <UiInput type="number" step="0.05" min="0" max="1" :model-value="s.ed().wake_word.sensitivity" @update:model-value="v => (s.ed().wake_word.sensitivity = toNum(v))" />
    </SettingsField>
    <p class="cs-note">
      VAD 模型、端点静音、阈值与 CPU/GPU 在「识别」Tab 配置；本卡保留唤醒词与对话时序。
    </p>
    <SettingsField v-if="s.editable.value" label="唤醒后等指令超时（ms）" en="Command timeout (ms)">
      <UiInput type="number" min="1" :model-value="s.ed().vad.answer_timeout_ms" @update:model-value="v => (s.ed().vad.answer_timeout_ms = toNum(v))" />
    </SettingsField>
    <!-- 打断播报（barge-in，docs/designs/02 批3）：助手说话时也可直接开口打断。
         默认关 = 播报期间停麦的旧行为。 -->
    <SettingsField v-if="s.editable.value" label="打断播报（助手说话时可直接开口打断）" en="Barge-in" row>
      <UiToggle :model-value="s.ed().vad.barge_in" @update:model-value="v => (s.ed().vad.barge_in = v)" />
    </SettingsField>
    <!-- 续聊窗口（docs/designs/03-A）：回合结束后的免唤醒接话窗口，0=关闭。 -->
    <SettingsField v-if="s.editable.value" label="续聊窗口（ms，结束后免唤醒直接说话；0=关）" en="Follow-up window (ms)">
      <UiInput type="number" min="0" :model-value="s.ed().vad.followup_window_ms" @update:model-value="v => (s.ed().vad.followup_window_ms = toNum(v))" />
    </SettingsField>
    <!-- 聆听空闲超时：唤醒进入聆听后 N 秒无实质信息 → 静待（麦保持本地 KWS 侦听）。 -->
    <SettingsField v-if="s.editable.value" label="聆听空闲超时（秒，无实质信息转入静待；0=永不）" en="Idle timeout (s)">
      <UiInput type="number" min="0" :model-value="s.ed().vad.listen_idle_s" @update:model-value="v => (s.ed().vad.listen_idle_s = toNum(v))" />
    </SettingsField>
  </SettingsCard>
</template>

<!-- 语音模块卡：唤醒词 / VAD 参数。Voice module card: wake word / VAD params. -->
<script setup lang="ts">
import { computed } from 'vue'
import SettingsField from './SettingsField.vue'
import SettingsCard from './SettingsCard.vue'
import BiLabel from './BiLabel.vue'
import { UiButton, UiInput, UiToggle } from '../../ui'
import { useSettings } from './useSettings'
import { notify } from '../../../composables/useToast'
import { settingsText as T } from '../../../locales/settings'

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/** ASR 转写模式标签（音频去哪转写）。ASR transcription-mode label (where audio is transcribed). */
const asrModeLabel = computed(() => {
  const m = s.sec('asr')?.mode
  return m === 'local' ? '本地' : m === 'hybrid' ? '混合' : '云端'
})

/** 转写模式的隐私口径一句话（与「语音识别」卡的分档说明一致）。 */
const asrPrivacyLine = computed(() => {
  switch (s.sec('asr')?.mode) {
    case 'local': return '唤醒链与作答/指令段的音频在本机转写、不上云（缺模型时明确报错，绝不偷偷上云）'
    case 'hybrid': return '本地优先，本地不可用/转写为空时才回落云端（回落即上传，审计记 fallback=1）'
    default: return '音频上传到当前 ASR profile 的服务商；下面的唤醒模式口径以此为前提'
  }
})

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
/* 隐私边界说明：与「权限」卡的同名段落保持一致的易读尺寸。
   Privacy note, matching the permissions card's note for readability. */
.cs-note { font-size: var(--fs-2xs); color: var(--text-3); line-height: 1.6; margin: 0; }
.cs-note strong { color: var(--text-2); }
.cs-note code {
  font-family: var(--font-mono); font-size: inherit;
  background: rgba(148, 163, 184, .12); border-radius: 3px; padding: 0 var(--sp-1);
}
/* 唤醒词行：一行一个关键词 + 删除按钮。Wake-keyword row: one keyword plus a delete button. */
.cs-kwrow { display: flex; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-2); }
.cs-mode-hint { font-size: var(--fs-2xs); color: var(--text-3); margin: var(--sp-q6) 0 0; line-height: 1.5; }
</style>
