import { createRouter, createWebHistory } from 'vue-router'
import StartPage from './views/StartPage.vue'
import ConsolePage from './views/ConsolePage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'start', component: StartPage },
    { path: '/console', name: 'console', component: ConsolePage },
  ],
})
