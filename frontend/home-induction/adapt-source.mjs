// Registered files stay exact; only the application's label and input bridge change.
export function adaptSource(source, runtimeAssets) {
  const once = (from, to) => {
    if (source.split(from).length !== 2) throw new Error(`Source anchor changed: ${from}`);
    source = source.replace(from, to);
  };
  for (const asset of runtimeAssets) {
    once(`src="${asset.url}"`, `src="/static/home-induction/runtime/${asset.file}"`);
  }
  // The source's Latin Inter webfont is not needed for the Chinese entry label.
  source = source.replace(/\s*<link[^>]+https:\/\/fonts\.(googleapis|gstatic)\.com[^>]*>/g, '');
  // The isolated variant hides this demo navigation icon; avoid its unused network lookup.
  once('icon="solar:atom-linear"', 'data-original-icon="solar:atom-linear"');
  // Hidden demo headlines have no innerText, so skip their empty GSAP target.
  once('tl.to(".mask-target", {', 'if (document.querySelector(".mask-target")) tl.to(".mask-target", {');
  once('>VALENCE CORE</span>', '>进入 API 测试</span>');
  // The user requested transparent outer edges over the existing glass card.
  once("canvas.getContext('webgl', { alpha: false, antialias: true })", "canvas.getContext('webgl', { alpha: true, premultipliedAlpha: false, antialias: true })");
  once("'  gl_FragColor = vec4(col, 1.0);',", `'  float surface = 1.0 - smoothstep(-0.003, 0.003, d);',
                    '  vec3 emission = max(col - vec3(0.039), vec3(0.0));',
                    '  float glowAlpha = clamp(max(emission.r, max(emission.g, emission.b)), 0.0, 1.0);',
                    '  vec3 glowColor = emission / max(glowAlpha, 0.0001);',
                    '  gl_FragColor = vec4(mix(glowColor, col, surface), mix(glowAlpha, 1.0, surface));',`);
  once('</head>', `<style>
html:root, html:root body { background: transparent !important; }
#bg-canvas { display: none !important; }
#btn { width: min(280px, 100vw); height: 96px; border: 0; }
#btn span { font-family: system-ui, sans-serif; letter-spacing: .06em; text-indent: .06em; }
</style></head>`);
  once('            initBackgroundGL();', '            // The homepage supplies its own Water background.');
  once('            initButtonGL();', `            initButtonGL();
            const entry = document.getElementById('btn');
            window.addEventListener('message', function(event) {
                if (event.source !== parent || event.data?.type !== 'workspace-induction') return;
                const kind = event.data.kind;
                if (kind === 'label') {
                    const label = entry.querySelector('span');
                    if (label && typeof event.data.label === 'string') label.textContent = event.data.label;
                    return;
                }
                if (!['mouseenter','mouseleave','focus','blur','mousedown','mouseup','click'].includes(kind)) return;
                entry.dispatchEvent(new MouseEvent(kind));
            });
            window.addEventListener('load', function() {
                parent.postMessage({type:'workspace-induction-ready'}, '*');
            }, {once:true});`);
  return source;
}
