<template>
  <div class="console-settings">
    <!-- 设置页头部：标题和说明文字。Settings page header: title and description. -->
    <div class="cs-head">
      <h2 class="cs-title"><UiIcon name="settings" :size="17" /> 设置</h2>
      <p class="cs-sub">左侧菜单切换模块；「语音」内用 Tab 分开概览 / 唤醒 / 识别 / 合成 / 硬件 / 高级。每个模块独立「保存 / 测试连接」</p>
    </div>

    <div class="cs-body">
      <!-- 左侧菜单：模块切换（LLM / ASR / TTS / 语音唤醒 / 高级设置）。Left sidebar menu: module switching (LLM / ASR / TTS / Voice Wake / Advanced). -->
      <SettingsMenu />

      <!-- 右侧内容区域：根据左侧菜单选择展示对应模块配置。Right content area: shows the module matching the left menu.
           检测结果不再占顶部条 —— toast 弹 3 秒 + 左侧菜单绿点（2026-10-11）。
           Test results no longer take a top bar — a 3s toast plus the left-menu green
           dot (2026-10-11). -->
      <div class="cs-main">
        <!-- editable 未加载完成前一张卡都不渲染 —— 外层一次守卫，替代原先 5 处重复的
             `s.editable.value &&` 前缀。activeMenu 初值即 'llm'，首屏若先渲染卡片会在
             sec(key).profiles 上取到 undefined。
             No card renders until editable has loaded — one outer guard replacing the 5 repeated
             `s.editable.value &&` prefixes. activeMenu starts as 'llm', so rendering the card
             first would read .profiles off undefined. -->
        <template v-if="s.editable.value">
          <!-- 服务模块（大模型 API Profile）。Service module (LLM API profile). -->
          <template v-for="def in sectionDefs" :key="def.key">
            <ServiceCard v-if="s.activeMenu.value === def.key" :section="def" />
          </template>

          <!-- 语音设置统一入口：概览/唤醒/识别/合成/硬件/高级。
               Single voice entry: overview / wake / recognition / synthesis / hardware / advanced. -->
          <VoiceSettingsPage v-if="s.activeMenu.value === 'voice'" />

          <!-- 权限模块：工具权限策略（层级默认 + 规则覆盖）。Permission module: tool permission policy. -->
          <PermissionsCard v-if="s.activeMenu.value === 'permissions'" />

          <!-- 高级模块：Agent / LLM 客户端 / 工具 / 服务器 参数配置。Advanced module: Agent / LLM client / Tools / Server settings. -->
          <AdvancedCard v-if="s.activeMenu.value === 'advanced'" />
        </template>

        <!-- 配置校验问题：检测到的错误和警告列表。Config validation issues: detected errors and warnings. -->
        <div v-if="s.issues.value.length" class="cs-issues">
          <p v-for="i in s.issues.value" :key="i.key" :class="'lv-' + i.level">[{{ i.level }}] {{ i.key }}：{{ i.message }}</p>
        </div>
      </div>
    </div>

    <!-- 密钥弹窗（无 props，状态取自 useSettings 单例）。API Key modal (no props; state from the useSettings singleton). -->
    <ApiKeyModal />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import AdvancedCard from './settings/AdvancedCard.vue'
import ApiKeyModal from './settings/ApiKeyModal.vue'
import PermissionsCard from './settings/PermissionsCard.vue'
import ServiceCard from './settings/ServiceCard.vue'
import VoiceSettingsPage from './settings/VoiceSettingsPage.vue'
import { useSettings } from './settings/useSettings'
import SettingsMenu from './settings/SettingsMenu.vue'
import { sectionDefs } from './settings/configDefs'
import { refreshVoiceStatus } from '../../composables/useVoiceModuleStatus'
import { UiIcon } from '../ui'

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

// useSettings 的 state 跨挂载存活，故每次进入设置页都重新拉取，避免展示陈旧配置。
// The useSettings state survives mount/unmount, so re-fetch on every entry to avoid stale config.
onMounted(() => {
  s.load()
  void refreshVoiceStatus()
})
</script>

<style scoped>
/* 布局（2026-10-11 第三轮裁定）：整页不滚动 —— 标题/菜单/卡头全部固定，只有每张卡的
   卡体（.cs-card-body，保存行以下）自己滚，滚动轴就在「保存」正下方，内容不带动页面。
   Layout (2026-10-11, third-round ruling): the page never scrolls — title, menu and card
   heads are all fixed; only each card's body (.cs-card-body, below the save row) scrolls,
   putting the scrollbar right under 保存 and keeping content from dragging the page. */
.console-settings {
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--sp-q14); flex: 1; min-height: 0; overflow: hidden;}
.cs-head { display: flex; flex-direction: column; gap: var(--sp-1); flex-shrink: 0; }
.cs-title {
  display: inline-flex; align-items: center; gap: var(--sp-2);
  font-size: var(--fs-lg); font-weight: 700; letter-spacing: .03em;
  color: var(--text-1); margin: 0;
}
.cs-title :deep(svg) { color: var(--brand-c2); }
.cs-sub { font-size: var(--fs-xs); color: var(--text-3); margin: 0; }

/* ── 左菜单 + 右内容（内容区 = 唯一滚动容器） ── */
.cs-body { display: flex; gap: var(--sp-4); align-items: stretch; flex: 1; min-height: 0; }
/* 左菜单样式（.cs-menu*）已随菜单组件搬进 settings/SettingsMenu.vue。
   The left menu's styles (.cs-menu*) moved into settings/SettingsMenu.vue with the component. */

/* 内容区不再整体滚动（2026-10-11 三轮裁定）：卡头固定在卡布局内、**卡体自己滚**——
   滚动轴落在每张卡「保存」行的正下方，标题/菜单/卡头都不随滚动移动，页面整体不动。
   The content area no longer scrolls as a whole (2026-10-11, third-round ruling): card
   heads are fixed in the card layout and **each card body scrolls internally** — the
   scrollbar sits directly under the card's save row; title, menu and card heads never
   move and the page stays put. */
.cs-main {
  flex: 1; min-width: 0; min-height: 0; overflow: hidden;
  display: flex; flex-direction: column; gap: var(--sp-q14);
}

/* 卡片的布局（超高处收缩 / 卡头固定 / 卡体自滚）已随外壳一并搬进 settings/SettingsCard.vue ——
   原先这里是 `:deep()` 反向穿透子组件，现在样式与被作用的元素同处一个组件，不再需要穿透。
   The card layout (shrink when tall / fixed head / self-scrolling body) moved into
   settings/SettingsCard.vue along with the shell — this used to be a `:deep()` reaching into
   the children; the styles and the elements they target now live in the same component, so no
   penetration is needed. */
/* 问题列表不参与收缩，让位给卡片。The issues list never yields space — the cards do. */
.cs-issues { flex-shrink: 0; }

.cs-issues { display: flex; flex-direction: column; gap: var(--sp-q6); }
.cs-issues p {
  font-size: var(--fs-2xs); margin: 0; line-height: 1.5;
  border-radius: var(--r-sm); padding: var(--sp-q6) var(--sp-q10);
}
.lv-error { color: #f87171; background: rgba(248, 113, 113, .07); }
.lv-warning { color: #fbbf24; background: rgba(251, 191, 36, .07); }
.lv-info { color: var(--text-3); background: rgba(148, 163, 184, .07); }
</style>
