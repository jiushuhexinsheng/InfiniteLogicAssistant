<template>
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
      <!-- 绿点只出现在有就绪语义的模块（LLM/ASR/TTS/语音）；权限与高级设置不渲染点。
           The dot only renders for modules with a readiness semantic (LLM/ASR/TTS/
           Voice); Permissions and Advanced get no dot at all. -->
      <i v-if="DOT_MENU_IDS.includes(m.id)" class="cs-menu-dot" :class="{ on: s.menuDot(m.id) }" title="绿点 = 就绪（密钥已设 / 测试通过 / 唤醒启用）"></i>
    </button>
    <div class="cs-menu-extra">
      <UiButton variant="secondary" size="sm" :disabled="s.detecting.value" @click="s.detectAll" block>
        {{ s.detecting.value ? '检测中…' : '检测全部' }}
      </UiButton>
    </div>
  </aside>
</template>

<!-- 设置页左侧菜单：模块切换 + 就绪绿点 + 「检测全部」。
     Settings left menu: module switching, readiness dots, and 检测全部.

     原先内联在 ConsoleSettings 的模板与 scoped 样式里；菜单是唯一仍整段内联的部分，而右侧
     6 张卡早已各自成组件 —— 抽出来后设置页两侧粒度一致。
     Previously inlined in ConsoleSettings' template and scoped styles. The menu was the last
     block still inlined while the 6 right-hand cards were already components; extracting it
     makes both sides of the settings page the same granularity. -->
<script setup lang="ts">
import { menuDefs } from './configDefs'
import { useSettings } from './useSettings'
import { UiButton, UiIcon } from '../../ui'

/** 设置页单例状态与操作（保留对象引用以维持响应式）。Settings singleton (kept as an object to preserve reactivity). */
const s = useSettings()

/** 渲染绿点的菜单模块（权限/高级设置无就绪语义，不渲染点）。
 *  Menu modules that render the dot (Permissions/Advanced have no readiness semantic,
 *  so they get no dot). */
const DOT_MENU_IDS = ['llm', 'asr', 'tts', 'voice']
</script>

<style scoped>
.cs-menu {
  width: 148px; flex-shrink: 0;
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
</style>
