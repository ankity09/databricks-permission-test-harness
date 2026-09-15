import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Vite outputs to dist/, which FastAPI serves as static files at /.
// Dev server proxies /api to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
