<template>
  <!-- 控制台侧边导航栏。Console sidebar navigation. -->
  <aside class="console-sidebar">
    <!-- 品牌标识区域。Brand identity area. -->
    <div class="sb-brand">
      <span class="sb-mark"><UiIcon name="infinity" :size="14" /></span>
      <div class="sb-name"><b>完整控制台</b><span class="mono">CONSOLE</span></div>
    </div>
    <!-- 导航标题。Navigation heading. -->
    <span class="sb-eyebrow mono">导航</span>
    <!-- 标签页导航列表。Tab navigation list. -->
    <UiNavItem
      v-for="t in CONSOLE_TABS"
      :key="t.key"
      :label="t.label"
      :icon="t.icon"
      :active="active === t.key"
      @click="emit('select', t.key)"
    />
    <!-- 语音唤醒状态底栏。Voice wake status footer. -->
    <div class="sb-foot">
      <UiStatusDot :color="wakeEnabled ? '#34d399' : '#64748b'" :size="7" :glow="wakeEnabled ? 8 : 0" />
      <div class="sb-foot-txt">
        <b>{{ wakeEnabled ? '语音唤醒已开启' : '语音唤醒未开启' }}</b>
        <!-- 双击悬浮球切换语音唤醒。Double-click the floating ball to toggle voice wake. -->
        <span class="mono">双击悬浮球切换</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
/**
 * 控制台侧边栏组件，包含品牌标识、标签页导航和语音唤醒状态显示。
 * Console sidebar component, contains brand identity, tab navigation and voice wake status display.
 */
import { CONSOLE_TABS, type ConsoleTabKey } from '../../composables/useConsole'
import { UiIcon, UiNavItem, UiStatusDot } from '../ui'

/** 属性：当前激活标签页和语音唤醒开关状态。Props: currently active tab key and voice wake toggle state. */
defineProps<{ active: ConsoleTabKey; wakeEnabled: boolean }>()
/** 事件：选择标签页。Event: select a tab. */
const emit = defineEmits<{ select: [key: ConsoleTabKey] }>()
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
  overflow-y: auto;
}
.sb-brand { display: flex; align-items: center; gap: 9px; padding: 0 6px 12px; }
.sb-mark {
  width: 26px; height: 26px; border-radius: 8px; flex-shrink: 0;
  background: var(--brand-grad); color: var(--text-on-brand);
  display: grid; place-items: center;
}
.sb-name { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.sb-name b { font-size: var(--fs-md); font-weight: 600; color: var(--text-1); }
.sb-name span { font-size: 9px; letter-spacing: .1em; color: var(--text-3); }
.sb-eyebrow {
  font-size: 10px; letter-spacing: .14em; color: var(--text-3);
  padding: 0 12px 4px;
}
.sb-foot {
  display: flex; align-items: center; gap: 8px;
  margin-top: auto; padding: 11px 10px;
  border: 1px solid rgba(52, 211, 153, .3); border-radius: var(--r-md);
  background: rgba(52, 211, 153, .06);
}
.sb-foot-txt { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.sb-foot-txt b { font-size: 11px; font-weight: 500; color: var(--ok); }
.sb-foot-txt span { font-size: 9px; color: var(--text-3); }
</style>
