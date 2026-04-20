import { defineConfig, loadEnv } from 'vite';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const host = process.env.TAURI_DEV_HOST;

export default defineConfig(async ({ mode }) => {
  // Load .env from project root (parent of seishin-client/) automatically
  const env = loadEnv(mode, resolve(__dirname, '..'), ['SEI_', 'VITE_', 'OPENCLAW_']);

  return {
    clearScreen: false,
    plugins: [{
      name: 'serve-onnx-wasm-mjs',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url?.includes('ort-wasm-simd-threaded.mjs')) {
            const file = resolve('node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs');
            res.setHeader('Content-Type', 'application/javascript');
            res.end(readFileSync(file, 'utf-8'));
            return;
          }
          next();
        });
      },
    }],
    server: {
      host: host || false,
      port: 1420,
      strictPort: true,
      hmr: host ? { protocol: 'ws', host, port: 1421 } : undefined,
      watch: { ignored: ['**/src-tauri/**'] },
    },
    resolve: {
      alias: {
        '@openclaw': resolve(__dirname, '../openclaw'),
        // openclaw/ lives outside seishin-client/ — resolve Tauri imports from here
        '@tauri-apps/plugin-shell': resolve(__dirname, 'node_modules/@tauri-apps/plugin-shell'),
        '@tauri-apps/plugin-opener': resolve(__dirname, 'node_modules/@tauri-apps/plugin-opener'),
        '@tauri-apps/plugin-fs': resolve(__dirname, 'node_modules/@tauri-apps/plugin-fs'),
        '@tauri-apps/api': resolve(__dirname, 'node_modules/@tauri-apps/api'),
        '@tauri-apps/plugin-http': resolve(__dirname, 'node_modules/@tauri-apps/plugin-http'),
      },
    },
    envPrefix: ['VITE_', 'SEI_'],
    define: {
      // Loaded from project root .env — no need to set in shell every time
      '__SEI_AUTH_TOKEN__': JSON.stringify(env.SEI_AUTH_TOKEN || ''),
      '__SEI_URL__': JSON.stringify(env.SEI_URL || ''),
      '__OPENCLAW_TOKEN__': JSON.stringify(env.OPENCLAW_TOKEN || ''),
    },
  };
});
