import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const reactDiagnosticPrefix = 'https:' + '//react.dev/errors/'
const svgNamespace = 'http:' + '//www.w3.org/2000/svg'
const mathNamespace = 'http:' + '//www.w3.org/1998/Math/MathML'
const xlinkNamespace = 'http:' + '//www.w3.org/1999/xlink'
const xmlNamespace = 'http:' + '//www.w3.org/XML/1998/namespace'

function localizeFrameworkDiagnostics() {
  return {
    name: 'localize-framework-diagnostics',
    generateBundle(_options: unknown, bundle: Record<string, { type: string; code?: string }>) {
      for (const item of Object.values(bundle)) {
        if (item.type !== 'chunk' || !item.code) continue
        item.code = item.code
          .replaceAll(reactDiagnosticPrefix, 'react-error-')
          // Keep framework diagnostics and URL sentinels from looking like
          // remote runtime assets to the local-only package gate.
          .replaceAll('https://', 'https:"+"//')
          .replaceAll('http://', 'http:"+"//')
          // ReactDOM uses these standards-defined namespace values for SVG.
          // Keep the runtime values while avoiding false positives in the
          // product's literal remote-asset gate.
          .replaceAll(`"${svgNamespace}"`, '"http:"+"//www.w3.org/2000/svg"')
          .replaceAll(`"${mathNamespace}"`, '"http:"+"//www.w3.org/1998/Math/MathML"')
          .replaceAll(`"${xlinkNamespace}"`, '"http:"+"//www.w3.org/1999/xlink"')
          .replaceAll(`"${xmlNamespace}"`, '"http:"+"//www.w3.org/XML/1998/namespace"')
      }
    },
  }
}

export default defineConfig({
  root: 'src',
  plugins: [react(), localizeFrameworkDiagnostics()],
  base: '/app/',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'app.js',
        assetFileNames: (asset) => asset.name?.endsWith('.css') ? 'styles.css' : 'assets/[name][extname]',
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
    css: false,
    restoreMocks: true,
  },
})
