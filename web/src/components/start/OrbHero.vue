<template>
  <!-- 光球动画区域（原光球下方的实时状态文字已移除，状态见顶部导航栏右侧） -->
  <div class="orb-wrap">
    <div class="orb" :class="asst.state.value">
      <span class="orb-halo"></span>
      <span class="orb-ripple"></span>
      <span class="orb-core">
        <UiIcon :name="asst.visual.value.icon" :size="30" />
      </span>
    </div>
  </div>

  <!-- 标题 -->
  <h1 class="title">无限逻辑</h1>
  <p class="subtitle">{{ subtitle }}</p>

  <!-- 操作按钮 -->
  <div class="actions">
    <UiButton variant="primary" @click="asst.expanded.value = true" aria-label="开始对话">
      <UiIcon name="messages-square" :size="16" /> 开始对话
    </UiButton>
    <UiButton variant="secondary" @click="asst.toggleWake()" :aria-label="asst.wakeEnabled.value ? '关闭语音唤醒' : '开启语音唤醒'">
      <UiIcon :name="asst.wakeEnabled.value ? 'stop' : 'mic'" :size="15" />
      {{ asst.wakeEnabled.value ? '关闭语音唤醒' : '开启语音唤醒' }}
    </UiButton>
    <UiButton variant="ghost" @click="gotoTtsSettings" aria-label="语音设置">
      <UiIcon name="settings" :size="15" /> 语音设置
    </UiButton>
  </div>
</template>

<!-- 起始页头部：光球 + 标题 + 副标题 + 动作按钮。
     Start-page hero: orb + title + subtitle + action buttons.

     ⚠️ 这是**多根组件**（fragment），刻意不加包裹元素 —— 这四块原本就是 `.hero` 这个 flex 列的
     直接子元素，靠 `.hero` 的 `gap: var(--sp-6)` 分隔。包一层 div 会多出一个 DOM 节点、改变间距
     归属，外观就不再逐像素相同了。
     ⚠️ This is a **multi-root** component (fragment) that deliberately adds no wrapper — these four
     blocks are direct children of `.hero`'s flex column and are spaced by its `gap: var(--sp-6)`.
     A wrapper div would inject a DOM node and re-parent the spacing, so the look would no longer
     be pixel-identical.

     入场动效（rise-in + 各块 animation-delay 分段）必须整体留在这里：它的作用对象就是这四个根
     元素，拆到别处会因 scope 分家而错位。
     The entrance animation (rise-in plus each block's animation-delay stagger) must stay here
     whole: its targets are exactly these four roots, and splitting it would misalign the staggers
     across scopes. -->
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAssistant } from '../../composables/useAssistant'
import { startSubtitle } from '../../composables/assistant/hints'
import { useConsole } from '../../composables/useConsole'
import { activeMenu } from '../console/settings/state'
import { UiButton, UiIcon } from '../ui'

const asst = useAssistant()
const router = useRouter()
const { activeTab } = useConsole()

/** 副标题：随唤醒开关走 + 露出双击通话入口（hints.ts 单一事实源）。Subtitle: wake-switch aware, exposes the double-click call entry (single source in hints.ts). */
const subtitle = computed(() => startSubtitle(asst.wakeEnabled.value, asst.wakeHint.value))

/**
 * 跳转到控制台「语音合成」设置页。
 * Navigate to the console's voice-synthesis settings page.
 *
 * 先设置目标 tab / 菜单再导航，保证落页即渲染语音合成区块
 * （activeTab 与 activeMenu 均为模块级单例，跨页共享）。
 * Set the target tab/menu before navigating so the destination renders the
 * TTS section immediately (both are module-level singletons shared across pages).
 */
function gotoTtsSettings() {
  activeTab.value = 'settings'
  activeMenu.value = 'tts'
  void router.push('/console')
}
</script>

<style scoped>
/* ── 光球 ── */
.orb-wrap { display: flex; flex-direction: column; align-items: center; gap: var(--sp-q10); }
.orb {
  position: relative; width: 116px; height: 116px; border-radius: 50%;
  background: var(--brand-grad); display: grid; place-items: center;
}
.orb-halo {
  position: absolute; inset: 10px; border-radius: 50%;
  background: var(--brand-grad); filter: blur(26px); opacity: .45;
  animation: orb-halo 5.5s ease-in-out infinite;
}
.orb-ripple {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1.5px solid var(--brand-c2); opacity: .7;
  animation: orb-ripple 3.4s ease-out infinite;
}
.orb-core {
  position: relative; width: 98px; height: 98px; border-radius: 50%;
  background: var(--bg-1);
  display: grid; place-items: center; color: var(--brand-c1);
}
.orb.listening .orb-ripple { animation-duration: 2s; }
.orb.recording .orb-ripple { animation-duration: 1.3s; }
.orb.recording .orb-core { animation: orb-breathe .7s ease-in-out infinite; }
@keyframes orb-breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
@keyframes orb-halo { 0%, 100% { opacity: .4; transform: scale(1); } 50% { opacity: .6; transform: scale(1.08); } }
@keyframes orb-ripple { 0% { transform: scale(1); opacity: .7; } 75%, 100% { transform: scale(1.75); opacity: 0; } }

/* ── 标题 ── */
.title {
  font-size: clamp(2.2rem, 6vw, 3rem); font-weight: 800; letter-spacing: .12em; margin: 0;
  background: linear-gradient(135deg, #c7d2fe 0%, #67e8f9 50%, #6ee7b7 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 0 26px rgba(103, 232, 249, .16));
}

.subtitle {
  font-size: var(--fs-lg); color: var(--text-2); letter-spacing: .05em; margin: 0;
  line-height: 1.5;
}

/* ── 操作按钮 ── */
.actions { display: flex; gap: var(--sp-q10); flex-wrap: wrap; justify-content: center; padding-top: var(--sp-q2); }

/* ── 入场动效（仅上半部分） ── */
.orb-wrap, .title, .subtitle, .actions {
  animation: rise-in .6s ease-out both;
}
.orb-wrap { animation-delay: .08s; }
.title { animation-delay: .14s; }
.subtitle { animation-delay: .2s; }
.actions { animation-delay: .26s; }
@keyframes rise-in { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
</style>
