import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  envDir: '../',
  server: {
    proxy: {
      '/dday': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/chat/stream': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
