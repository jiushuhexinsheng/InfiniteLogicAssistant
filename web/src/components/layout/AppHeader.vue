<template>
  <header class="app-header">
    <button class="ah-brand" type="button" @click="router.push('/')" aria-label="返回首页">
      <span class="ah-mark"><UiIcon name="infinity" :size="16" /></span>
      <span class="ah-name">
        <b>无限逻辑</b>
        <span class="ah-name-en mono">INFINITE LOGIC</span>
      </span>
    </button>
    <nav class="ah-nav" aria-label="主导航">
      <button
        class="ah-nav-item"
        :class="{ active: route.path === '/' }"
        type="button"
        @click="router.push('/')"
        :aria-current="route.path === '/' ? 'page' : undefined"
      >开始页</button>
      <button
        class="ah-nav-item"
        :class="{ active: route.path === '/console' }"
        type="button"
        @click="router.push('/console')"
        :aria-current="route.path === '/console' ? 'page' : undefined"
      >控制台</button>
    </nav>
    <!-- 右侧系统信息（承接原控制台状态点 + 原模式开关位置）。
         System info pill on the right (absorbs the console status dot and old mode switch spot). -->
    <NavSystemInfo />
  </header>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { UiIcon } from '../ui'
import NavSystemInfo from './NavSystemInfo.vue'

const router = useRouter()
const route = useRoute()
</script>

<style scoped>
.app-header {
  width: 100%; height: var(--header-h); flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 var(--sp-6);
  background: var(--bg-1);
  border-bottom: 1px solid var(--border-base);
}
.ah-brand {
  display: flex; align-items: center; gap: var(--sp-2);
  background: none; border: none; cursor: pointer; padding: var(--sp-2);
}
.ah-mark {
  width: 32px; height: 32px; border-radius: var(--r-md);
  background: var(--brand-grad); color: var(--text-on-brand);
  display: grid; place-items: center; flex-shrink: 0;
}
/* 品牌名双行：中文 + 英文小字（与控制台侧栏 sb-name 同构）。
   Two-line brand: Chinese + English caption (mirrors sb-name in the console sidebar). */
.ah-name { display: flex; flex-direction: column; gap: 1px; min-width: 0; text-align: left; }
.ah-name b { font-size: var(--fs-lg); font-weight: 600; color: var(--text-1); line-height: 1.2; }
.ah-name-en { font-size: 9px; letter-spacing: .1em; color: var(--text-3); line-height: 1.2; }
.ah-nav {
  display: flex; gap: var(--sp-1); padding: var(--sp-1);
  border-radius: var(--r-full); background: var(--bg-2);
  border: 1px solid var(--border-base);
}
.ah-nav-item {
  border: none; cursor: pointer; font-family: inherit;
  font-size: var(--fs-sm);
  padding: var(--sp-2) var(--sp-4); border-radius: var(--r-full);
  background: transparent; color: var(--text-2);
  min-height: var(--min-target-size);
}
.ah-nav-item:hover {
  background: var(--surface-control-hover);
  color: var(--text-1);
}
.ah-nav-item.active {
  background: var(--brand-c2);
  color: var(--text-on-brand);
  font-weight: 600;
}

/* 窄屏：先收起品牌文字，给导航与系统信息胶囊让位。
   Narrow screens: drop the brand word first to make room. */
@media (max-width: 480px) {
  .ah-name { display: none; }
  .app-header { padding: 0 var(--sp-3); }
}
</style>
