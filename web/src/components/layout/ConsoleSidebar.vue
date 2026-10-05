<template>
  <!-- 控制台侧边导航栏。Console sidebar navigation. -->
  <aside class="console-sidebar">
    <!-- 品牌标识区域：仅英文标识。Brand area: English caption only. -->
    <div class="sb-brand">
      <span class="sb-name mono">CONSOLE</span>
    </div>
    <!-- 中间导航区单独滚动，保证底栏（唤醒状态 + 清空）始终可见。
         The nav region scrolls on its own so the footer stays pinned and visible. -->
    <div class="sb-nav">
      <!-- 标签页导航列表。Tab navigation list. -->
      <UiNavItem
        v-for="t in CONSOLE_TABS"
        :key="t.key"
        :label="t.label"
        :icon="t.icon"
        :active="active === t.key"
        @click="emit('select', t.key)"
      />
    </div>
    <!-- 底栏：语音唤醒状态 + 清空对话（原控制台顶栏按钮移此）。
         Footer: wake status + clear conversation (moved from the old console header). -->
    <div class="sb-foot-stack">
      <div class="sb-foot">
        <UiStatusDot :color="wakeEnabled ? '#34d399' : '#64748b'" :size="7" :glow="wakeEnabled ? 8 : 0" />
        <div class="sb-foot-txt">
          <b>{{ wakeEnabled ? '语音唤醒已开启' : '语音唤醒未开启' }}</b>
          <!-- 双击悬浮球开通话（唤醒入口在球上的 mic 徽章）。Double-click the floating ball to start a call (wake stays on the ball's mic badge). -->
          <span class="mono">双击悬浮球开通话</span>
        </div>
      </div>
      <UiButton variant="secondary" size="sm" hover="danger" block @click="emit('clear')">清空对话</UiButton>
    </div>
  </aside>
</template>

<script setup lang="ts">
/**
 * 控制台侧边栏组件，包含品牌标识、标签页导航、语音唤醒状态与清空对话按钮。
 * Console sidebar: brand identity, tab nav, wake status and clear-conversation button.
 */
import { CONSOLE_TABS, type ConsoleTabKey } from '../../composables/useConsole'
import { UiButton, UiNavItem, UiStatusDot } from '../ui'

/** 属性：当前激活标签页和语音唤醒开关状态。Props: currently active tab key and voice wake toggle state. */
defineProps<{ active: ConsoleTabKey; wakeEnabled: boolean }>()
/** 事件：选择标签页、清空对话。Events: select tab, clear conversation. */
const emit = defineEmits<{ select: [key: ConsoleTabKey]; clear: [] }>()
</script>

<style scoped>
.console-sidebar {
  width: var(--nav-width); flex-shrink: 0;
  display: flex; flex-direction: column; gap: 7px;
  padding: 16px 12px;
  border: 1px solid var(--glass-border); border-radius: var(--r-xl);
  background: var(--surface-raised); backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  box-shadow: var(--shadow-2);
  overflow: hidden; /* 整体不滚，仅 .sb-nav 滚动，底栏常驻。Only .sb-nav scrolls; the footer stays pinned. */
}
.sb-nav {
  flex: 1; min-height: 0; overflow-y: auto;
  display: flex; flex-direction: column; gap: 7px;
}
.sb-brand { padding: 0 6px 12px; }
/* 仅英文标识：等宽字 + 字距，作为侧栏标题。English-only caption: mono + tracking, acts as the sidebar title. */
.sb-name {
  font-size: var(--fs-md); font-weight: 600;
  letter-spacing: .12em; color: var(--text-1);
}
.sb-foot-stack {
  margin-top: auto;
  display: flex; flex-direction: column; gap: 7px;
}
.sb-foot {
  display: flex; align-items: center; gap: 8px;
  padding: 11px 10px;
  border: 1px solid rgba(52, 211, 153, .3); border-radius: var(--r-md);
  background: rgba(52, 211, 153, .06);
}
.sb-foot-txt { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.sb-foot-txt b { font-size: 11px; font-weight: 500; color: var(--ok); }
.sb-foot-txt span { font-size: 9px; color: var(--text-3); }
</style>
