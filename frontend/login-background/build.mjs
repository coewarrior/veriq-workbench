import { build } from 'esbuild';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
const root = path.dirname(fileURLToPath(import.meta.url));
const vendor = path.join(root, 'vendor/threeui');
const manifest = JSON.parse(await fs.readFile(path.join(vendor, 'source-bundle.json')));
const support = JSON.parse(await fs.readFile(path.join(vendor, 'support-manifest.json')));
const registered = [...manifest.files, ...manifest.assets, ...support];
for (const f of registered) {
  const data = await fs.readFile(path.join(vendor, f.path));
  if (createHash('sha256').update(data).digest('hex') !== f.sha256) throw Error(`Source hash mismatch: ${f.path}`);
}
const output = path.resolve(root, '../../api_test_tool/static/sylva-background');
await fs.mkdir(output, { recursive: true });
await fs.cp(path.join(vendor, 'public/landing-pages'), path.join(output, 'landing-pages'), { recursive: true });
const source = await fs.readFile(path.join(vendor, 'src/shaders/landing-pages/LandingPages.tsx'), 'utf8');
// Select the complete authored Sylva section verbatim. The catalog's other landing
// pages import unregistered assets; they are not part of this login entry point.
// All registered originals remain byte-exact and are checked above on every build.
const marker = 'export const SYLVA_HERO_VARIANTS =';
if (source.split(marker).length !== 2) throw Error('Sylva source boundary changed');
const imports = `import { useMemo } from 'react';
import { splitTypographyProps, usePageTypography, type PageTypographyProps } from './pageTypography';
import { LandingPageFrame, type LandingPageProps } from './LandingPageFrame';
import { SYLVA_TYPOGRAPHY } from './pageRecipes';
import innerGreenSource from '../sylva-living-world/sources/inner-green-3d.html?raw';
import { MAPLE_AUTUMN_STYLE, SAKURA_SUNSET_STYLE, SEQUOIA_MIST_STYLE,
applyMapleAutumnVariant, applySakuraSunsetVariant, applySequoiaMistVariant } from '../sylva-living-world/SylvaLivingWorldScene';\n`;
await build({
  absWorkingDir: root, entryPoints: { background: 'mount.tsx' }, outdir: output,
  bundle: true, loader: { '.woff2': 'file' }, format: 'esm', jsx: 'automatic', target: ['es2020'], minify: true,
  define: { 'process.env.NODE_ENV': '"production"' }, legalComments: 'linked',
  plugins: [{ name: 'exact-sylva-source', setup(b) {
    b.onResolve({filter: /^@designcodeio\/threeui$/}, () => ({path: 'sylva-entry', namespace: 'sylva'}));
    b.onLoad({filter: /.*/, namespace: 'sylva'}, () => ({contents: imports + source.slice(source.indexOf(marker)), loader:'tsx', resolveDir:path.join(vendor,'src/shaders/landing-pages')}));
    b.onResolve({filter: /^@designcodeio\/threeui\/style\.css$/}, () => ({path: path.join(vendor,'src/shaders/threeui.css')}));
    b.onResolve({filter: /\?raw$/}, args => ({path:path.resolve(args.resolveDir,args.path.slice(0,-4)),namespace:'raw'}));
    b.onLoad({filter: /.*/,namespace:'raw'}, async args => ({contents:await fs.readFile(args.path,'utf8'),loader:'text'}));
  }}],
});
const html = await fs.readFile(path.join(vendor,'public/landing-pages/inner-green-3d.html'),'utf8');
const metal = html.match(/<script>\s*(\(function \(\) \{[\s\S]*?mountLiquidMetal[\s\S]*?)<\/script>/)?.[1];
const css = html.slice(html.indexOf('  .liquid-stage{'), html.indexOf('  /* ── play button'));
if (!metal || !css.includes('.liquid-stage.press')) throw Error('Native metal source boundary changed');
// Mount the original five-pass control in the real login form. If WebGL2 is
// unavailable leave the accessible HTML submit button intact.
await fs.writeFile(path.join(output,'metal.js'), `try { const probe=document.createElement('canvas'); const gl=probe.getContext('webgl2'); if(gl){gl.getExtension('WEBGL_lose_context')?.loseContext();\n${metal}\n} } catch (error) { console.warn('Metal decoration unavailable',error); }\n`);
await fs.writeFile(path.join(output,'metal.css'), css);
for(const file of ['LICENSE','FONT-LICENSES.md','ASSET-LICENSES.md']) await fs.copyFile(path.join(vendor,file),path.join(output,file+'.txt'));
await fs.writeFile(path.join(root,'build-manifest.json'),JSON.stringify({source:'https://threeui.com/source-code/sylva-hero.json',revision:'05f359ce157a',variant:'living-green',files:registered.map(({path,sha256})=>({path,sha256}))},null,2)+'\n');
console.log(`Verified ${registered.length} sources/assets; built Sylva and native liquid metal.`);
