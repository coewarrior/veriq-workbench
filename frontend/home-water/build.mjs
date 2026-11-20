import { build } from 'esbuild';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { adaptSource } from './adapt-source.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
const vendor = path.join(root, 'vendor/threeui');
const bundle = JSON.parse(await fs.readFile(path.join(vendor, 'source-bundle.json'), 'utf8'));
for (const file of bundle.files) {
  const content = await fs.readFile(path.join(vendor, file.path));
  if (createHash('sha256').update(content).digest('hex') !== file.sha256) {
    throw new Error(`Registered source changed: ${file.path}`);
  }
}
const output = path.resolve(root, '../../api_test_tool/static/home-water');
const brand = await fs.readFile(path.resolve(root, '../../api_test_tool/static/brand-orbit.svg'), 'utf8');
await fs.mkdir(output, { recursive: true });
const result = await build({
  absWorkingDir: root,
  entryPoints: { water: 'mount.tsx' },
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
    name: 'threeui-raw-html',
    setup(build) {
      build.onResolve({ filter: /\.html\?raw$/ }, args => ({
        path: path.resolve(args.resolveDir, args.path.slice(0, -4)), namespace: 'threeui-html',
      }));
      build.onLoad({ filter: /.*/, namespace: 'threeui-html' }, async args => ({
        contents: adaptSource(await fs.readFile(args.path, 'utf8'), brand), loader: 'text',
      }));
    },
  }],
});
await fs.writeFile(path.join(root, 'build-manifest.json'), JSON.stringify({
  source: 'https://threeui.com/source-code/elemental-water.json',
  revision: '7a6871fe99fa',
  variant: 'water',
  branding: { asset: 'api_test_tool/static/brand-orbit.svg', sha256: createHash('sha256').update(brand).digest('hex') },
  registeredFiles: bundle.files.map(({path, sha256}) => ({path, sha256})),
  outputs: Object.fromEntries(Object.entries(result.metafile.outputs).map(([file, value]) => [path.basename(file), { bytes: value.bytes }])),
}, null, 2) + '\n');
for (const name of ['LICENSE', 'FONT-LICENSES.md']) {
  await fs.copyFile(path.join(vendor, name), path.join(output, name === 'LICENSE' ? 'THREEUI-LICENSE.txt' : name));
}
console.log(`Verified ${bundle.files.length} exact Water source files; built ${Object.keys(result.metafile.outputs).length} assets.`);
