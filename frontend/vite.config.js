import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

const projectRoot = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const { BACKEND_PORT = '8001' } = loadEnv(mode, projectRoot, 'BACKEND_')
  return {
    envDir: projectRoot,
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: { '/api': `http://127.0.0.1:${BACKEND_PORT}` },
    },
  }
})
