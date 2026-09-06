import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8800',
        changeOrigin: true,
      },
      '/qr': {
        target: 'http://127.0.0.1:8800',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: path.resolve(__dirname, '..', 'static'),
    emptyOutDir: true,
  },
})
