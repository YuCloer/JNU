import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/resume': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/interview': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/jd': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
