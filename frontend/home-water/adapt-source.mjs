// Application-specific branding and full-page pointer forwarding. The registered
// ThreeUI files stay byte-for-byte intact and are verified before this adapter runs.
export function adaptSource(source, brandSvg) {
  const replaceOnce = (before, after) => {
    if (source.split(before).length !== 2) throw new Error('Water source integration anchor changed: ' + before);
    source = source.replace(before, after);
  };
  replaceOnce("<script>\n'use strict';", `<script type="module">
'use strict';
const workspaceBrand = new Image();
workspaceBrand.src = ${JSON.stringify('data:image/svg+xml;base64,' + Buffer.from(brandSvg).toString('base64'))};
await workspaceBrand.decode();`);
  replaceOnce("  const ctx = c.getContext('2d');", `  const ctx = c.getContext('2d');
  if (pathStr === LOGO_PATHS.openai) {
    const box = SDF_SIZE * 0.60, off = (SDF_SIZE - box) / 2;
    ctx.drawImage(workspaceBrand, off, off, box, box);
    return ctx.getImageData(0, 0, SDF_SIZE, SDF_SIZE);
  }`);
  replaceOnce('    this.aspect = w / h;', `    this.aspect = w / h;
    // Reserve clear space for the brand: left of desktop cards, above phone cards.
    if (this.opts.sim) this.opts.shift = r.width <= 900 ? [0, 0.23] : [-0.28, 0];`);
  replaceOnce('const t0 = performance.now();', `window.addEventListener('message', event => {
  if (event.source !== parent || event.data?.type !== 'workspace-water-pointer') return;
  const { kind, x, y } = event.data;
  if (!['pointermove', 'pointerdown', 'pointerup', 'pointerleave'].includes(kind) || !Number.isFinite(x) || !Number.isFinite(y)) return;
  const el = document.querySelector('[data-fx="water"]');
  const r = el.getBoundingClientRect();
  el.dispatchEvent(new PointerEvent(kind, {clientX:r.left + Math.max(0, Math.min(1, x)) * r.width, clientY:r.top + Math.max(0, Math.min(1, y)) * r.height}));
});
const t0 = performance.now();`);
  return source;
}
