<template>
  <div class="console-settings">
    <!-- 设置页头部：标题和说明文字。Settings page header: title and description. -->
    <div class="cs-head">
      <h2 class="cs-title"><UiIcon name="settings" :size="17" /> 设置</h2>
      <p class="cs-sub">左侧菜单切换模块，每个模块独立「保存 / 测试连接」，密钥通过弹出框设置</p>
    </div>

    <div class="cs-body">
      <!-- 左侧菜单：模块切换（LLM / ASR / TTS / 语音唤醒 / 高级设置）。Left sidebar menu: module switching (LLM / ASR / TTS / Voice Wake / Advanced). -->
      <aside class="cs-menu">
        <button
          v-for="m in menuDefs"
          :key="m.id"
          class="cs-menu-item"
          :class="{ on: s.activeMenu.value === m.id }"
          @click="s.activeMenu.value = m.id"
        >
          <UiIcon :name="m.icon" :size="14" />
          <span>{{ m.label }}</span>
          <i class="cs-menu-dot" :class="{ on: s.menuDot(m.id) }" title="密钥已设置"></i>
        </button>
        <div class="cs-menu-extra">
          <UiButton variant="secondary" size="sm" :disabled="s.detecting.value" @click="s.detectAll" block>
            {{ s.detecting.value ? '检测中…' : '检测全部' }}
          </UiButton>
        </div>
      </aside>

      <!-- 右侧内容区域：根据左侧菜单选择展示对应模块配置。Right content area: shows the module matching the left menu. -->
      <div class="cs-main">
        <!-- 连接状态条：展示各服务模块的连通性检测结果。Connection status bar: connectivity results per service module. -->
        <div v-if="Object.keys(s.connResults.value).length" class="cs-conn">
          <UiChip v-for="c in Object.values(s.connResults.value)" :key="c.name" :tone="connTone(c.status)" :dot="false">
            {{ c.name }} {{ connStatusText(c.status) }}
          </UiChip>
        </div>

        <!-- 服务模块：LLM / ASR / TTS（仅在 activeMenu 匹配时显示）。Service modules: LLM / ASR / TTS (shown when activeMenu matches).
             必须同时等 editable 加载完成：activeMenu 初值即 'llm'，首屏若先渲染卡片会在 sec(key).profiles 上取到 undefined。
             Must also wait for editable to load: activeMenu starts as 'llm', so rendering the card first would read .profiles off undefined. -->
        <template v-for="def in sectionDefs" :key="def.key">
          <ServiceCard v-if="s.editable.value && s.activeMenu.value === def.key" :section="def" />
        </template>

        <!-- 语音模块：唤醒词 + VAD + 本地播报配置。Voice module: wake word + VAD + local speech settings. -->
        <VoiceCard v-if="s.editable.value && s.activeMenu.value === 'voice'" />

        <!-- 高级模块：Agent / LLM 客户端 / 工具 / 服务器 参数配置。Advanced module: Agent / LLM client / Tools / Server settings. -->
        <AdvancedCard v-if="s.editable.value && s.activeMenu.value === 'advanced'" />

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
import ServiceCard from './settings/ServiceCard.vue'
import VoiceCard from './settings/VoiceCard.vue'
import { useSettings } from './settings/useSettings'
import { menuDefs, sectionDefs } from './settings/configDefs'
import { UiButton, UiChip, UiIcon } from '../ui'

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/**
 * 将连通性状态映射为 UI 色调。
 * Map a connectivity status to a UI tone.
 *
 * @param status 连通性状态。Connectivity status.
 * @returns UI 色调。The UI tone.
 */
function connTone(status: string): 'ok' | 'warn' | 'err' | 'info' | 'neutral' {
  return status === 'ok' ? 'ok' : status === 'skip' ? 'neutral' : 'err'
}

/**
 * 将连通性状态转为中文文本。
 * Convert a connectivity status to Chinese text.
 *
 * @param status 连通性状态。Connectivity status.
 * @returns 中文状态文本。The Chinese status text.
 */
function connStatusText(status: string): string {
  return status === 'ok' ? '✓ 连通' : status === 'skip' ? '跳过' : '✗ 失败'
}

// useSettings 的 state 跨挂载存活，故每次进入设置页都重新拉取，避免展示陈旧配置。
// The useSettings state survives mount/unmount, so re-fetch on every entry to avoid stale config.
onMounted(() => { s.load(); s.loadCatalog() })
</script>

<style scoped>
.console-settings {
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px; flex: 1; min-height: 0; overflow-y: auto;}
.cs-head { display: flex; flex-direction: column; gap: 4px; }
.cs-title {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: var(--fs-lg); font-weight: 700; letter-spacing: .03em;
  color: var(--text-1); margin: 0;
}
.cs-title :deep(svg) { color: var(--brand-c2); }
.cs-sub { font-size: var(--fs-xs); color: var(--text-3); margin: 0; }

/* ── 左菜单 + 右内容 ── */
.cs-body { display: flex; gap: 16px; align-items: flex-start; }
.cs-menu {
  width: 148px; flex-shrink: 0; position: sticky; top: 12px;
  display: flex; flex-direction: column; gap: 3px;
}
.cs-menu-item {
  display: flex; align-items: center; gap: 8px;
  font-size: var(--fs-xs); color: var(--text-2); text-align: left;
  background: rgba(15, 23, 42, .55); border: 1px solid transparent;
  border-radius: var(--r-sm); padding: 7px 10px; cursor: pointer;
  transition: color var(--dur-fast), border-color var(--dur-fast), background var(--dur-fast);
}
.cs-menu-item:hover { color: var(--brand-c2); }
.cs-menu-item.on {
  color: var(--brand-c2); border-color: var(--brand-c2);
  background: rgba(11, 17, 32, .75);
}
.cs-menu-dot {
  margin-left: auto; width: 7px; height: 7px; border-radius: 50%;
  background: rgba(148, 163, 184, .25);
}
.cs-menu-dot.on { background: #34d399; box-shadow: 0 0 6px rgba(52, 211, 153, .6); }
.cs-menu-extra { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border-soft); }

.cs-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }

.cs-conn { display: flex; gap: 8px; flex-wrap: wrap; }

.cs-issues { display: flex; flex-direction: column; gap: 6px; }
.cs-issues p {
  font-size: var(--fs-2xs); margin: 0; line-height: 1.5;
  border-radius: var(--r-sm); padding: 6px 9px;
}
.lv-error { color: #f87171; background: rgba(248, 113, 113, .07); }
.lv-warning { color: #fbbf24; background: rgba(251, 191, 36, .07); }
.lv-info { color: var(--text-3); background: rgba(148, 163, 184, .07); }
</style>
