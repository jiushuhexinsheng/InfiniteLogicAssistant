<template>
  <!-- 应用顶部导航栏。Application top navigation header. -->
  <header class="app-header">
    <!-- 品牌按钮：点击跳转首页。Brand button: click to navigate to home page. -->
    <button class="ah-brand" type="button" @click="router.push('/')">
      <span class="ah-mark"><UiIcon name="infinity" :size="16" /></span>
      <span class="ah-name">无限逻辑</span>
      <span class="ah-sub">VOICE · OMNICONTROL</span>
    </button>
    <!-- 主导航区域。Main navigation area. -->
    <nav class="ah-nav">
      <!-- 开始页导航项。Start page navigation item. -->
      <button class="ah-nav-item" :class="{ active: route.path === '/' }" type="button" @click="router.push('/')">开始页</button>
      <!-- 控制台导航项。Console navigation item. -->
      <button class="ah-nav-item" :class="{ active: route.path === '/console' }" type="button" @click="router.push('/console')">控制台</button>
    </nav>
  </header>
</template>

<script setup lang="ts">
/**
 * 应用顶部导航栏组件，包含品牌标识和页面导航。
 * Application top navigation header component, contains brand logo and page navigation.
 */
import { useRoute, useRouter } from 'vue-router'
import { UiIcon } from '../ui'

/** 路由实例，用于页面跳转。Router instance for page navigation. */
const router = useRouter()
/** 当前路由信息，用于判断激活状态。Current route info for determining active state. */
const route = useRoute()
</script>

<style scoped>
.app-header {
  width: 100%; height: 64px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 32px;
  background: rgba(2, 6, 23, .72);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  border-bottom: 1px solid var(--border-soft);
  position: sticky; top: 0; z-index: 20;
}
.ah-brand { display: flex; align-items: center; gap: 10px; background: none; border: none; cursor: pointer; padding: 0; }
.ah-mark {
  width: 30px; height: 30px; border-radius: 9px;
  background: var(--brand-grad); color: var(--text-on-brand);
  display: grid; place-items: center;
}
.ah-name { font-size: 18px; font-weight: 700; color: var(--text-1); }
.ah-sub { font-family: var(--font-mono); font-size: 10px; letter-spacing: .14em; color: var(--text-3); }
.ah-nav {
  display: flex; gap: 4px; padding: 4px;
  border-radius: 999px; background: var(--surface-control);
  border: 1px solid var(--border-soft);
}
.ah-nav-item {
  border: none; cursor: pointer; font-family: inherit; font-size: 13px;
  padding: 7px 16px; border-radius: 999px;
  background: transparent; color: var(--text-2);
  transition: background var(--dur-fast), color var(--dur-fast);
}
.ah-nav-item.active { background: var(--brand-grad); color: var(--text-on-brand); font-weight: 700; }
</style>
