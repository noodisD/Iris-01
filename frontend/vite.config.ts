import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // import.meta.url rather than __dirname: the config is ESM ("type":
    // "module"), and Vite 6 onward loads it natively instead of bundling it to
    // CJS, so __dirname is not defined at that point.
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy /api/* to the IRIS FastAPI backend during dev.
      // The client (src/api/client.ts) keeps BASE empty and calls /api/* on
      // this dev server, so requests are same-origin and the proxy forwards
      // them here — avoids the cookie + wildcard-CORS problem.
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
