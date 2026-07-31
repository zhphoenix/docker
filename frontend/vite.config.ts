import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3001,
    proxy: {
      '/v1': {
        target: 'http://localhost:8100',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8100',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8100',
        changeOrigin: true,
      },
      '/metrics': {
        target: 'http://localhost:8100',
        changeOrigin: true,
      },
    },
  },
})
