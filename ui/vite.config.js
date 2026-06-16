import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api -> backend FastAPI để khỏi lo CORS khi dev
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // ws: true so the /api/ws WebSocket is proxied to the backend too (live updates)
      '/api': { target: 'http://localhost:8000', ws: true },
    },
  },
})
