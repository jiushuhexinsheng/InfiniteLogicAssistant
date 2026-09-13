import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8520',
        changeOrigin: true,
      },
    },
  },
  // 不再设置 publicDir：原先指向的 web/public/（Vosk WASM 引擎 + 唤醒词模型）已随
  // 唤醒链路重构一并删除，该目录不存在，留着只是死配置。
  // No publicDir any more: the web/public/ it pointed at (the Vosk WASM engine and the wake-word
  // model) was deleted along with the wake pipeline rework, so the entry was dead config.
})
