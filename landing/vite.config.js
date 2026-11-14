import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    // three.js alone is most of the bundle; one file is fine for a single page
    chunkSizeWarningLimit: 700,
  },
});
