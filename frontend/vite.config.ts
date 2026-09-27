import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { createReadStream, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * Talk mode's voice detection runs in the browser, and its model and runtime
 * are served from IRIS itself, never a CDN (ADR-0025). They are copied from
 * node_modules into assets/vad/, which the server already serves, only when
 * built; the dev server streams them from node_modules.
 */
const VAD_FILES: Record<string, string> = {
  'vad.worklet.bundle.min.js': '@ricky0123/vad-web/dist/vad.worklet.bundle.min.js',
  'silero_vad_v5.onnx': '@ricky0123/vad-web/dist/silero_vad_v5.onnx',
  'ort-wasm-simd-threaded.wasm': 'onnxruntime-web/dist/ort-wasm-simd-threaded.wasm',
  'ort-wasm-simd-threaded.mjs': 'onnxruntime-web/dist/ort-wasm-simd-threaded.mjs',
};
const fromModules = (path: string) => fileURLToPath(new URL(`./node_modules/${path}`, import.meta.url));
const VAD_TYPES: Record<string, string> = {
  js: 'text/javascript', mjs: 'text/javascript', wasm: 'application/wasm', onnx: 'application/octet-stream',
};

function vadAssets(): Plugin {
  return {
    name: 'iris-vad-assets',
    configureServer(server) {
      server.middlewares.use('/assets/vad/', (req, res, next) => {
        const name = (req.url ?? '').replace(/^\//, '').split('?')[0];
        const source = VAD_FILES[name];
        if (!source) return next();
        res.setHeader('Content-Type', VAD_TYPES[name.split('.').pop() ?? ''] ?? 'application/octet-stream');
        createReadStream(fromModules(source)).pipe(res);
      });
    },
    generateBundle() {
      for (const [name, source] of Object.entries(VAD_FILES)) {
        this.emitFile({ type: 'asset', fileName: `assets/vad/${name}`, source: readFileSync(fromModules(source)) });
      }
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), vadAssets()],
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
