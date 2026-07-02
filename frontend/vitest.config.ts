import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// Kept separate from vite.config.ts so the production `tsc` build never typechecks the
// `test` key (vitest bundles a different vite version than the app's).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    // Pure lib functions only; JSX compiles to plain objects, so no DOM is needed.
    environment: 'node',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
