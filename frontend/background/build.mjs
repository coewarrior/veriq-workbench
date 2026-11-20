import { build } from 'esbuild';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const root = path.dirname(fileURLToPath(import.meta.url));
const vendor = path.join(root, 'vendor/threeui');
const bundle = JSON.parse(await fs.readFile(path.join(vendor, 'source-bundle.json'), 'utf8'));
for (const file of bundle.files) {
  const content = await fs.readFile(path.join(vendor, file.path));
  if (createHash('sha256').update(content).digest('hex') !== file.sha256) {
    throw new Error(`Registered source changed: ${file.path}`);
  }
}
const output = path.resolve(root, '../../api_test_tool/static/signal-background');
await fs.mkdir(output, { recursive: true });
// Mirror the authored scripts for intranet clients; keep registered source intact.
const runtimeRoot = path.join(root, 'vendor/runtime');
const runtimeAssets = JSON.parse(await fs.readFile(path.join(runtimeRoot, 'manifest.json'), 'utf8'));
await fs.mkdir(path.join(output, 'runtime'), { recursive: true });
for (const asset of runtimeAssets) {
  const content = await fs.readFile(path.join(runtimeRoot, asset.file));
  if (createHash('sha256').update(content).digest('hex') !== asset.sha256) {
    throw new Error(`Runtime dependency changed: ${asset.file}`);
  }
  await fs.writeFile(path.join(output, 'runtime', asset.file), content);
}
const result = await build({
  absWorkingDir: root,
  entryPoints: { background: 'mount.tsx' },
  outdir: output,
  bundle: true,
  format: 'esm',
  splitting: true,
  jsx: 'automatic',
  target: ['es2020'],
  minify: true,
  define: { 'process.env.NODE_ENV': '"production"' },
  entryNames: '[name]',
  chunkNames: '[name]-[hash]',
  assetNames: 'fonts/[name]',
  loader: { '.woff2': 'file' },
  legalComments: 'linked',
  metafile: true,
  plugins: [{
    name: 'threeui-raw-html',
    setup(build) {
      build.onResolve({ filter: /\.html\?raw$/ }, args => ({
        path: path.resolve(args.resolveDir, args.path.slice(0, -4)), namespace: 'threeui-html',
      }));
      build.onLoad({ filter: /.*/, namespace: 'threeui-html' }, async args => {
        let contents = await fs.readFile(args.path, 'utf8');
        if (path.basename(args.path) === 'signal-particles.html') {
          for (const asset of runtimeAssets) {
            const original = `src="${asset.url}"`;
            if (!contents.includes(original)) throw new Error(`Missing authored dependency: ${asset.url}`);
            contents = contents.replace(original, `src="/static/signal-background/runtime/${asset.file}"`);
          }
        }
        return { contents, loader: 'text' };
      });
    },
  }],
});
await fs.writeFile(path.join(root, 'build-manifest.json'), JSON.stringify({
  source: 'https://threeui.com/source-code/predictive-arc.json',
  revision: 'fa86582fc870',
  variant: 'signal-particles',
  runtimeAssets,
  registeredFiles: bundle.files.map(({path, sha256}) => ({path, sha256})),
  outputs: Object.fromEntries(Object.entries(result.metafile.outputs).map(([file, value]) => [path.basename(file), { bytes: value.bytes }])),
}, null, 2) + '\n');
console.log(`Verified ${bundle.files.length} exact source files; built ${Object.keys(result.metafile.outputs).length} assets.`);
await fs.writeFile(path.join(output, 'frame.html'), `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://code.iconify.design https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://hoirqrkdgbmvpwutwuwj.supabase.co; connect-src https://api.iconify.design https://api.simplesvg.com https://api.unisvg.com; frame-src 'self' about:; base-uri 'self'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>Signal Particles</title><link rel="stylesheet" href="./background.css">
<style>html,body,#signal-background,.shader-frame{width:100%;height:100%;margin:0;overflow:hidden}body{background:#0a0a0a}</style>
</head><body><div id="signal-background"></div><script type="module" src="./background.js"></script></body></html>\n`);
await fs.copyFile(path.join(vendor, 'LICENSE'), path.join(output, 'THREEUI-LICENSE.txt'));
await fs.copyFile(path.join(vendor, 'FONT-LICENSES.md'), path.join(output, 'FONT-LICENSES.md'));
