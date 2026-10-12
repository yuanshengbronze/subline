import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';
await mkdir('extension/dist', { recursive: true });
await build({ entryPoints: ['extension/background.ts','extension/content.ts','extension/popup.tsx'], bundle: true, outdir: 'extension/dist', format: 'iife', target: 'chrome120', minify: true, jsx: 'automatic' });
await Promise.all(['manifest.json','popup.html','popup.css'].map(file => copyFile('extension/'+file,'extension/dist/'+file)));
