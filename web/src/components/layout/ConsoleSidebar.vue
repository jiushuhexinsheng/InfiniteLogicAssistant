<template>
  <!-- 控制台侧边导航栏：可折叠（2026-10-11 用户要求）；「新建对话 / 清空对话」并排置顶，
       折叠后只剩图标（历史记录等导航仍可点）。
       Console sidebar: collapsible (2026-10-11 user request); "New / Clear conversation"
       sit side by side at the top; collapsed shows icons only (History and the rest stay
       reachable). -->
  <aside class="console-sidebar" :class="{ collapsed: sidebarCollapsed }">
    <!-- 品牌标识 + 折叠开关。Brand caption + collapse toggle. -->
    <div class="sb-brand">
      <span v-if="!sidebarCollapsed" class="sb-name mono">CONSOLE</span>
      <button
        class="sb-fold"
        type="button"
        :title="sidebarCollapsed ? '展开侧栏' : '折叠侧栏'"
        @click="toggleSidebar()"
      >
        <UiIcon name="chevron-down" :size="14" class="sb-fold-ico" :class="{ right: sidebarCollapsed }" />
      </button>
    </div>

    <!-- 新建 / 清空（并排；折叠后为图标按钮）。New / Clear (side by side; icon-only when collapsed). -->
    <div class="sb-actions">
      <UiButton variant="secondary" size="sm" class="sb-act" @click="emit('new')">
        <UiIcon name="plus" :size="13" /><span class="sa-txt">新建</span>
      </UiButton>
      <UiButton variant="secondary" size="sm" hover="danger" class="sb-act" @click="emit('clear')">
        <UiIcon name="trash" :size="13" /><span class="sa-txt">清空</span>
      </UiButton>
    </div>

    <!-- 中间导航区单独滚动（含「历史」入口）。Nav region scrolls on its own (incl. History). -->
    <div class="sb-nav">
      <UiNavItem
        v-for="t in CONSOLE_TABS"
        :key="t.key"
        :label="t.label"
        :icon="t.icon"
        :active="active === t.key"
        @click="emit('select', t.key)"
      />
    </div>

    <!-- 底栏：语音唤醒状态（清空已上移）。Footer: wake status (Clear moved up). -->
    <div class="sb-foot-stack">
      <div class="sb-foot">
        <UiStatusDot :color="wakeEnabled ? '#34d399' : '#64748b'" :size="7" :glow="wakeEnabled ? 8 : 0" />
        <div class="sb-foot-txt" v-if="!sidebarCollapsed">
          <b>{{ wakeEnabled ? '语音唤醒已开启' : '语音唤醒未开启' }}</b>
          <span class="mono">双击悬浮球开通话</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
/**
 * 控制台侧边栏组件：品牌 + 折叠开关、新建/清空、标签导航、唤醒状态。
 * Console sidebar: brand + collapse toggle, New/Clear, tab nav, wake status.
 */
import { CONSOLE_TABS, useConsole, type ConsoleTabKey } from '../../composables/useConsole'
import { UiButton, UiIcon, UiNavItem, UiStatusDot } from '../ui'

/** 属性：当前激活标签页和语音唤醒开关状态。Props: currently active tab key and voice wake toggle state. */
defineProps<{ active: ConsoleTabKey; wakeEnabled: boolean }>()
/** 事件：选择标签页、新建对话、清空对话。Events: select tab, new conversation, clear conversation. */
const emit = defineEmits<{ select: [key: ConsoleTabKey]; clear: []; new: [] }>()

/** 折叠态（useConsole 单例 + localStorage 持久化）。Collapse state (useConsole singleton + localStorage). */
const { sidebarCollapsed, toggleSidebar } = useConsole()
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
  overflow: hidden; /* 整体不滚，仅 .sb-nav 滚动。Only .sb-nav scrolls. */
  transition: width var(--dur-base) var(--ease-out), padding var(--dur-base) var(--ease-out);
}

/* ── 折叠态：只留图标（导航/动作/状态点仍可用）。Collapsed: icons only (nav/actions/status stay usable). */
.console-sidebar.collapsed { width: 62px; padding: 14px 8px; gap: 6px; }
.console-sidebar.collapsed .sb-name { display: none; }
.console-sidebar.collapsed .sa-txt { display: none; }
.console-sidebar.collapsed .sb-foot-txt { display: none; }
.console-sidebar.collapsed .sb-actions { flex-direction: column; }
.console-sidebar.collapsed .sb-act { justify-content: center; padding-left: 0; padding-right: 0; }
.console-sidebar.collapsed :deep(.ui-nav-label) { display: none; }
.console-sidebar.collapsed :deep(.ui-nav-item) { justify-content: center; padding-left: 0; padding-right: 0; }
.console-sidebar.collapsed .sb-foot { justify-content: center; padding-left: 0; padding-right: 0; }

.sb-brand {
  display: flex; align-items: center; justify-content: space-between; gap: 4px;
  padding: 0 6px 10px;
}
/* 仅英文标识：等宽字 + 字距，作为侧栏标题。English-only caption: mono + tracking, sidebar title. */
.sb-name {
  font-size: var(--fs-md); font-weight: 600;
  letter-spacing: .12em; color: var(--text-1);
}
/* 折叠开关：折叠后占满品牌行居中。Collapse toggle: centered in the brand row when collapsed. */
.sb-fold {
  margin-left: auto;
  display: grid; place-items: center;
  width: 22px; height: 22px; border-radius: var(--r-sm);
  border: none; background: none; color: var(--text-3); cursor: pointer;
  transition: color var(--dur-fast), background var(--dur-fast);
}
.sb-fold:hover { color: var(--brand-c2); background: var(--surface-control); }
.console-sidebar.collapsed .sb-fold { margin-left: auto; }
.sb-fold-ico { transform: rotate(90deg); }          /* 收起：箭头朝左 */
.sb-fold-ico.right { transform: rotate(-90deg); }   /* 展开：箭头朝右 */

/* 新建 / 清空并排。New / Clear side by side. */
.sb-actions { display: flex; gap: 6px; }
.sb-act { flex: 1; justify-content: center; gap: 4px; }

.sb-nav {
  flex: 1; min-height: 0; overflow-y: auto;
  display: flex; flex-direction: column; gap: 7px;
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
