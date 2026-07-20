import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
  // loadEnv reads from .env, .env.local, etc. using an empty prefix to capture all vars.
  const env = loadEnv(mode, path.resolve(__dirname, '..'), '');

  // Backend port for the dev-server proxy target (default: 8080).
  const backendPort = env.EXPLORER_PORT || '8080';
  // Frontend dev server port (default: 5173).
  const frontendPort = parseInt(env.EXPLORER_FRONTEND_PORT || '5173', 10);

  const backendTarget = `http://localhost:${backendPort}`;

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: frontendPort,
      proxy: {
        '/api': backendTarget,
        '/healthz': backendTarget,
        '/readyz': backendTarget,
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  };
});
