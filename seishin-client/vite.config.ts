import { defineConfig } from 'vite';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const host = process.env.TAURI_DEV_HOST;

export default defineConfig(async () => ({
  clearScreen: false,
  plugins: [{
    name: 'serve-onnx-wasm-mjs',
    configureServer(server) {
      // ONNX runtime dynamically imports .mjs files at runtime.
      // Vite blocks imports from public/ and can't resolve them from root.
      // Serve them from node_modules with correct Content-Type.
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
    hmr: host
      ? {
          protocol: 'ws',
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ['**/src-tauri/**'],
    },
  },
  resolve: {
    alias: {
      '@openclaw': resolve(__dirname, '../openclaw'),
      // openclaw/ is outside seishin-client/ — resolve its Tauri imports from here
      '@tauri-apps/plugin-shell': resolve(__dirname, 'node_modules/@tauri-apps/plugin-shell'),
      '@tauri-apps/plugin-opener': resolve(__dirname, 'node_modules/@tauri-apps/plugin-opener'),
      '@tauri-apps/plugin-fs': resolve(__dirname, 'node_modules/@tauri-apps/plugin-fs'),
      '@tauri-apps/api': resolve(__dirname, 'node_modules/@tauri-apps/api'),
    },
  },
  envPrefix: ['VITE_', 'SEI_'],
  define: {
    '__SEI_AUTH_TOKEN__': JSON.stringify(process.env.SEI_AUTH_TOKEN || 'test-token-change-me'),
  },
}));
