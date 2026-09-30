import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/* The pages are served by experimental/webui/serve.py next to /api; in
   development Vite proxies /api to that server so the pages read real recorded
   runs. Two entries: the run viewer and the RSI Studio. The Studio imports
   ui-web's stylesheets from the repository, so the dev server may read them
   (paths are relative to this folder, where Vite runs). */
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: { input: { index: 'index.html', studio: 'studio.html' } },
  },
  server: {
    proxy: { '/api': 'http://127.0.0.1:8765', '/files': 'http://127.0.0.1:8765' },
    fs: { allow: ['.', '../../ui-web/src'] },
  },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'] },
})
