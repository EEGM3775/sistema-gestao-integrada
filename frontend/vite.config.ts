import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
    dedupe: ['react', 'react-dom'],
  },
  server: {
    host: true,
    proxy: {
      '/api':     { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/auth':    { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/odm-api': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/drone':   { target: 'http://127.0.0.1:8088', changeOrigin: true },
      '/ws':      { target: 'http://127.0.0.1:8080', changeOrigin: true, ws: true },
    },
  },
})
