import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/recharts/')) return 'recharts-core';
          if (id.includes('node_modules/victory-vendor/')) return 'recharts-d3';
          if (id.includes('node_modules/d3-')) return 'recharts-d3';
          if (id.includes('node_modules/react-smooth/')) return 'recharts-d3';
          if (id.includes('node_modules/react-transition-group/')) return 'recharts-d3';
        },
      },
    },
  },
});
