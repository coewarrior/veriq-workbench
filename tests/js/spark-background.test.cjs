const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const frontend = path.join(root, 'frontend/spark-background');
const vendor = path.join(frontend, 'vendor/threeui');
const output = path.join(root, 'api_test_tool/static/spark-background');
const read = file => fs.readFileSync(file, 'utf8');
const expected = {
  'src/shaders/spark-badge/SparkBadge.tsx': '2968baef448957765473ccd031f4337d376dbace5e8ec5434d0a57299ffecdda',
  'src/shaders/spark-badge/spark-badge.html': 'a8eefdee0d87deefae9b8b8dac4d79c0ee41447578a78090cad9c956e33ccf90',
  'src/shaders/threeui.css': 'efe4447139f1358dd8e9be68edf6fa46cbefbd1de423a4d6c439ca61d2c8eccf',
};

test('the complete SparkBadge registered bundle and all three source files remain byte-exact', () => {
  const bundle = JSON.parse(read(path.join(vendor, 'source-bundle.json')));
  assert.equal(bundle.id, 'spark-badge');
  assert.deepEqual(bundle.files.map(file => file.path).sort(), Object.keys(expected).sort());
  assert.deepEqual(bundle.assets, []);
  for (const file of bundle.files) {
    const content = fs.readFileSync(path.join(vendor, file.path));
    assert.equal(createHash('sha256').update(content).digest('hex'), expected[file.path]);
    assert.equal(file.sha256, expected[file.path]);
    assert.deepEqual(content, Buffer.from(file.code));
  }
});

test('the configured React scene selects badge and preserves all five 1.00 props', () => {
  const scene = read(path.join(frontend, 'Scene.tsx'));
  assert.match(scene, /import \{ SparkBadge \} from "@designcodeio\/threeui"/);
  assert.match(scene, /import "@designcodeio\/threeui\/style\.css"/);
  assert.match(scene, /variant="badge"/);
  assert.match(scene, /sourceUrl="\/static\/spark-background\/veriq-badge\.html"/);
  for (const prop of ['speed', 'particleAmount', 'rainAmount', 'turbulence', 'spread']) {
    assert.ok(scene.includes(prop + '={1.00}'));
  }
});

test('the deployed scene document is the exact authored Canvas 2D source', () => {
  const scene = fs.readFileSync(path.join(output, 'spark-badge.html'));
  assert.deepEqual(scene, fs.readFileSync(path.join(vendor, 'src/shaders/spark-badge/spark-badge.html')));
  assert.match(scene.toString(), /getContext\('2d', \{ alpha: false \}\)/);
  assert.match(scene.toString(), /adaptive load governor/);
});

test('VERIQ changes only the wordmark block and records its own output hash', async () => {
  const { createVeriqBadgeSource, WORDMARK_START, WORDMARK_END } = await import('../../frontend/spark-background/wordmark.mjs');
  const original = read(path.join(vendor, 'src/shaders/spark-badge/spark-badge.html'));
  const branded = read(path.join(output, 'veriq-badge.html'));
  assert.equal(branded, createVeriqBadgeSource(original));
  assert.ok(branded.startsWith(original.slice(0, original.indexOf(WORDMARK_START))));
  assert.ok(branded.endsWith(original.slice(original.indexOf(WORDMARK_END))));
  assert.match(branded, /const str = 'VERIQ'/);
  assert.doesNotMatch(branded, /Codex/);
  const manifest = JSON.parse(read(path.join(frontend, 'build-manifest.json')));
  assert.equal(manifest.sceneUrl, '/static/spark-background/veriq-badge.html');
  assert.equal(manifest.branding.wordmark, 'VERIQ');
  assert.equal(manifest.branding.sha256, createHash('sha256').update(branded).digest('hex'));
  assert.throws(() => createVeriqBadgeSource('<html>unrecognized source</html>'), /unavailable/);
  assert.throws(() => createVeriqBadgeSource(original.replace("const str = 'Codex'", "const str = 'other'")), /unavailable/);
});

test('all five VERIQ letter paths are finite, centred and fit the original badge window', async () => {
  const { VERIQ_WORDMARK } = await import('../../frontend/spark-background/wordmark.mjs');
  const strokes = [];
  const context = () => {
    let points;
    const point = (x, y) => {
      assert.ok(Number.isFinite(x) && Number.isFinite(y));
      assert.ok(x >= 0.342 * 768 && x <= 0.658 * 768);
      assert.ok(y >= 0.420 * 768 && y <= 0.600 * 768);
      points.push([x, y]);
    };
    return {
      beginPath() { points = []; }, moveTo: point, lineTo: point,
      bezierCurveTo(...args) { for (let i = 0; i < args.length; i += 2) point(args[i], args[i + 1]); },
      ellipse(x, y, rx, ry) { point(x - rx, y - ry); point(x + rx, y + ry); },
      stroke() { assert.ok(points.length >= 2); strokes.push(points); },
    };
  };
  const gm = context(), ge = context(), document = { documentElement: { dataset: {} } };
  vm.runInNewContext(VERIQ_WORDMARK, { S: 768, TAU: 2 * Math.PI, gm, ge, document, W2G: () => '#fff', both: fn => { fn(gm); fn(ge); } });
  assert.equal(strokes.length, 10);
  assert.equal(document.documentElement.dataset.sparkWordmark, 'VERIQ');
});

test('platform branding is consistent without renaming the real Codex integration', () => {
  const html = read(path.join(root, 'api_test_tool/static/index.html'));
  const login = read(path.join(root, 'api_test_tool/static/login.html'));
  const ui = read(path.join(root, 'api_test_tool/static/ui-workflow.js'));
  assert.match(html, /<span>探真<small>VERIQ · API 测试<\/small>/);
  assert.match(html, /aria-label="探真 VERIQ 首页"/);
  assert.match(login, /<span>探真<small>VERIQ<\/small>/);
  assert.match(login, /AI 驱动的测试与质量平台/);
  assert.match(ui, /需求与页面测试 · 探真 VERIQ/);
  assert.match(ui, /VERIQ · 需求与页面测试/);
  assert.match(html, /Codex 授权/);
  assert.match(html, /交给 Codex 完成任务/);
  assert.match(html, /id="mcp-title">授权 Codex 访问测试台/);
});

test('the workspace uses one local, decorative background below interactive controls', () => {
  const html = read(path.join(root, 'api_test_tool/static/index.html'));
  const theme = read(path.join(root, 'api_test_tool/static/signal-theme.css'));
  assert.equal((html.match(/id="signal-background-frame"/g) || []).length, 1);
  assert.doesNotMatch(html, /spark-background-frame/);
  assert.match(html, /src="\/static\/signal-background\/frame\.html"[^>]*aria-hidden="true"[^>]*tabindex="-1"/);
  assert.match(theme, /#signal-background-frame\s*\{[^}]*position: fixed;[^}]*z-index: 0;[^}]*pointer-events: none;/);
  assert.match(theme, /\.shell\s*\{[^}]*z-index: 1;/);
  const workflow = read(path.join(root, 'api_test_tool/static/ui-workflow.js'));
  const flowStyles = read(path.join(root, 'api_test_tool/static/ui-flow.css'));
  assert.doesNotMatch(workflow, /getElementById\('signal-background-frame'\).*remove\(/);
  assert.doesNotMatch(flowStyles, /body\.ui-workspace[^{}]*:is\(\.panel,\.stepper\)\s*\{[^}]*background:/);
  assert.doesNotMatch(flowStyles, /body\.ui-workspace[^{}]*:is\(\.panel,\.stepper\)[^{}]*\{[^}]*backdrop-filter:\s*none/);
});

test('the local host loads no remote documentation or runtime CDN', () => {
  const frame = read(path.join(output, 'frame.html'));
  assert.match(frame, /id="spark-background"/);
  assert.match(frame, /src="\.\/background\.js"/);
  assert.match(frame, /connect-src 'none'/);
  assert.doesNotMatch(frame, /https?:\/\//);
  const component = read(path.join(vendor, 'src/shaders/spark-badge/SparkBadge.tsx'));
  assert.match(component, /sandbox="allow-scripts"/);
  assert.match(component, /visibilitychange/);
});
