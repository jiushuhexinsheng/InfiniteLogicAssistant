/**
 * 路由配置
 * Router configuration
 */
import { createRouter, createWebHistory } from 'vue-router'
import StartPage from './views/StartPage.vue'
import ConsolePage from './views/ConsolePage.vue'

/**
 * 创建并导出路由实例
 * Create and export router instance
 */
export const router = createRouter({
  // 使用 HTML5 History 模式 / Use HTML5 History mode
  history: createWebHistory(),
  // 路由配置 / Route configuration
  routes: [
    /** 首页路由 / Home page route */
    { path: '/', name: 'start', component: StartPage },
    /** 控制台路由 / Console page route */
    { path: '/console', name: 'console', component: ConsolePage },
  ],
})
