/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The Python program serves the built page at /ui/ and the API at /api/.
const apiPort = process.env.EFACTURA_API_PORT ?? '8765'

export default defineConfig({
  base: '/ui/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  build: {
    // Built straight into the Python package, so `efactura serve` needs nothing else.
    outDir: '../src/efactura/ui',
    emptyOutDir: true,
  },
  test: {
    // The page is used on a PC in Romania, and some days show their edges only on its clock (the change of the hour).
    env: { TZ: 'Europe/Bucharest' },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // changeOrigin: the API only trusts requests addressed to its own host and port.
      '/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
    },
  },
})
