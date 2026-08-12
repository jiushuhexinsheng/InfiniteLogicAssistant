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
  publicDir: 'public',
  // 多页：控制台(index) + 桌面悬浮球(ball)
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        ball: resolve(__dirname, 'ball.html'),
      },
    },
  },
})
