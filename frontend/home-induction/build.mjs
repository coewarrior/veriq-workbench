import { build } from 'esbuild';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { adaptSource } from './adapt-source.mjs';
const root = path.dirname(fileURLToPath(import.meta.url));
const vendor = path.join(root, 'vendor/threeui');
const bundle = JSON.parse(await fs.readFile(path.join(vendor, 'source-bundle.json'), 'utf8'));
const hash = data => createHash('sha256').update(data).digest('hex');
for (const file of bundle.files) {
  if (hash(await fs.readFile(path.join(vendor, file.path))) !== file.sha256) throw new Error(`Registered source changed: ${file.path}`);
}
const output = path.resolve(root, '../../api_test_tool/static/home-induction');
const runtimeRoot = path.resolve(root, '../background/vendor/runtime');
const runtimeAssets = JSON.parse(await fs.readFile(path.join(runtimeRoot, 'manifest.json'), 'utf8')).filter(a => !a.file.startsWith('ScrollTrigger'));
await fs.mkdir(path.join(output, 'runtime'), {recursive:true});
for (const asset of runtimeAssets) {
  const bytes = await fs.readFile(path.join(runtimeRoot, asset.file));
  if (hash(bytes) !== asset.sha256) throw new Error(`Runtime changed: ${asset.file}`);
  await fs.writeFile(path.join(output, 'runtime', asset.file), bytes);
}
const result = await build({
  absWorkingDir: root, entryPoints: {induction:'mount.tsx'}, outdir:output,
  bundle:true, format:'esm', jsx:'automatic', target:['es2020'], minify:true,
  define:{'process.env.NODE_ENV':'"production"'}, assetNames:'fonts/[name]',
  loader:{'.woff2':'file'}, legalComments:'linked', metafile:true,
  plugins:[{name:'registered-variant', setup(build) {
    build.onResolve({filter:/\.html\?raw$/}, args => ({path:path.resolve(args.resolveDir,args.path.slice(0,-4)),namespace:'threeui-html'}));
    build.onLoad({filter:/.*/,namespace:'threeui-html'}, async args => {
      // This registered bundle supplies just Induction. Other variants are never exported.
      if (path.basename(args.path) !== 'valence-core.html') return {contents:'',loader:'text'};
      return {contents:adaptSource(await fs.readFile(args.path,'utf8'),runtimeAssets),loader:'text'};
    });
  }}],
});
await fs.writeFile(path.join(root,'build-manifest.json'),JSON.stringify({
  source:'https://threeui.com/source-code/induction-button.json',revision:'6f56c4f91814',variant:'induction-button',
  registeredFiles:bundle.files.map(({path,sha256})=>({path,sha256})),runtimeAssets,
  outputs:Object.fromEntries(Object.entries(result.metafile.outputs).map(([file,value])=>[path.basename(file),{bytes:value.bytes}]))
},null,2)+'\n');
for (const name of ['LICENSE','FONT-LICENSES.md']) await fs.copyFile(path.join(vendor,name),path.join(output,name === 'LICENSE' ? 'THREEUI-LICENSE.txt' : name));
console.log('Verified all 3 registered Induction files and authored runtime dependencies.');
