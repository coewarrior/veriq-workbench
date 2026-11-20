import { build } from 'esbuild';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { createVeriqBadgeSource } from './wordmark.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
const vendor = path.join(root, 'vendor/threeui');
const bundle = JSON.parse(await fs.readFile(path.join(vendor, 'source-bundle.json'), 'utf8'));
const expected = {
  'src/shaders/spark-badge/SparkBadge.tsx': '2968baef448957765473ccd031f4337d376dbace5e8ec5434d0a57299ffecdda',
  'src/shaders/spark-badge/spark-badge.html': 'a8eefdee0d87deefae9b8b8dac4d79c0ee41447578a78090cad9c956e33ccf90',
  'src/shaders/threeui.css': 'efe4447139f1358dd8e9be68edf6fa46cbefbd1de423a4d6c439ca61d2c8eccf',
};
if (bundle.id !== 'spark-badge' || bundle.files.length !== Object.keys(expected).length || bundle.assets.length) {
  throw new Error('Unexpected SparkBadge source bundle');
}
for (const file of bundle.files) {
  const content = await fs.readFile(path.join(vendor, file.path));
  const digest = createHash('sha256').update(content).digest('hex');
  if (digest !== expected[file.path] || file.sha256 !== digest || !content.equals(Buffer.from(file.code))) {
    throw new Error(`Registered source changed: ${file.path}`);
  }
}

// Reuse the already vendored official font and license files without altering
// the registered shared stylesheet or requiring public CDNs at runtime.
const supportRoot = path.resolve(root, '../background/vendor/threeui');
const support = [
  { path: 'src/shaders/fonts/fragment-mono.woff2', sha256: '4f4dc27f4a770c0d02fde800daa836c8adc0d1e423b28da74baaf0d1cc3ab96c' },
  { path: 'LICENSE', sha256: 'b2a071ba22fefd803f4e9d1f5c777dd79c62d191695586a1a73fd4d0ebd051c6' },
  { path: 'FONT-LICENSES.md', sha256: '05f4ec01ea30193a48878689209f39a2b6541e44291ad8ddc1909a1c1b8b6eeb' },
];
for (const file of support) {
  const content = await fs.readFile(path.join(supportRoot, file.path));
  if (createHash('sha256').update(content).digest('hex') !== file.sha256) {
    throw new Error(`Support dependency changed: ${file.path}`);
  }
}

const output = path.resolve(root, '../../api_test_tool/static/spark-background');
await fs.mkdir(output, { recursive: true });
const result = await build({
  absWorkingDir: root,
  entryPoints: { background: 'mount.tsx' },
  outdir: output,
  bundle: true,
  format: 'esm',
  jsx: 'automatic',
  target: ['es2020'],
  minify: true,
  define: { 'process.env.NODE_ENV': '"production"' },
  assetNames: 'fonts/[name]',
  loader: { '.woff2': 'file' },
  legalComments: 'linked',
  metafile: true,
  plugins: [{
    name: 'registered-threeui-font',
    setup(build) {
      build.onResolve({ filter: /^\.\/fonts\/fragment-mono\.woff2$/ }, () => ({
        path: path.join(supportRoot, 'src/shaders/fonts/fragment-mono.woff2'),
      }));
    },
  }],
});
await fs.copyFile(path.join(vendor, 'src/shaders/spark-badge/spark-badge.html'), path.join(output, 'spark-badge.html'));
const brandedScene = createVeriqBadgeSource(await fs.readFile(path.join(output, 'spark-badge.html'), 'utf8'));
await fs.writeFile(path.join(output, 'veriq-badge.html'), brandedScene);
await fs.copyFile(path.join(supportRoot, 'LICENSE'), path.join(output, 'THREEUI-LICENSE.txt'));
await fs.copyFile(path.join(supportRoot, 'FONT-LICENSES.md'), path.join(output, 'FONT-LICENSES.md'));
await fs.writeFile(path.join(output, 'frame.html'), `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'none'; frame-src 'self'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>SparkBadge Background</title><link rel="stylesheet" href="./background.css">
<style>html,body,#spark-background,.shader-frame{width:100%;height:100%;margin:0;overflow:hidden}body{background:#000}</style>
</head><body><div id="spark-background"></div><script type="module" src="./background.js"></script></body></html>
`);
await fs.writeFile(path.join(root, 'build-manifest.json'), JSON.stringify({
  source: 'https://threeui.com/source-code/spark-badge.json',
  revision: 'a8eefdee0d87',
  variant: 'badge',
  props: { speed: 1, particleAmount: 1, rainAmount: 1, turbulence: 1, spread: 1 },
  sceneUrl: '/static/spark-background/veriq-badge.html',
  branding: { wordmark: 'VERIQ', sha256: createHash('sha256').update(brandedScene).digest('hex') },
  registeredFiles: bundle.files.map(({ path, sha256 }) => ({ path, sha256 })),
  support,
  outputs: Object.fromEntries(Object.entries(result.metafile.outputs).map(([file, value]) => [path.basename(file), { bytes: value.bytes }])),
}, null, 2) + '\n');
console.log(`Verified ${bundle.files.length} exact SparkBadge sources; built ${Object.keys(result.metafile.outputs).length} assets.`);
