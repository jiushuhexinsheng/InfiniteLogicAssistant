/**
 * 应用入口文件
 * Application entry file
 */
import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
// 导入全局样式 / Import global styles
import './styles/tokens.css'
import './styles/app.css'

// 创建 Vue 应用实例并挂载到 #app 元素
// Create Vue application instance and mount to #app element
createApp(App).use(router).mount('#app')
