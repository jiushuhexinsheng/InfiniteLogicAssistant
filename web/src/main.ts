import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './styles/tokens.css'
import './styles/app.css'

createApp(App).use(router).mount('#app')
