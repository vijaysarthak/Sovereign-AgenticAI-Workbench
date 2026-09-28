import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/auth': 'http://localhost:8080',
      '/me': 'http://localhost:8080',
      '/ask': 'http://localhost:8080',
      '/documents': 'http://localhost:8080',
      '/ledger': 'http://localhost:8080',
      '/grants': 'http://localhost:8080',
      '/admin': 'http://localhost:8080',
      '/conversations': 'http://localhost:8080',
      '/report': 'http://localhost:8080',
      '/models': 'http://localhost:8080',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
