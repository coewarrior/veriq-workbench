# ThreeUI Signal Particles background

Both `/api-testing` and `/ui-testing` mount the local `signal-background/frame.html` through the decorative `signal-background-frame`. The frame renders the requested `Scene.tsx` with the exact configured props: `variant="signal-particles"`, `mode="dark"`, speed 1, hue 0, saturation 1, brightness 1.

## Source provenance

All 16 registered files from <https://threeui.com/source-code/predictive-arc.json> are stored byte-for-byte in `vendor/threeui/src/`. The complete downloaded JSON is retained in `source-bundle.json`. Every build checks the SHA-256 for all registered files and stops on a mismatch. Registered revision: `fa86582fc870`; the SHA-256 of the complete downloaded JSON (which is distinct from the catalog revision) is `138646da953c1bad8264d10cc7087f0108d189ebe819beb362117a16b07d1149`.

The local `@designcodeio/threeui` package exports the registered `PredictiveArcCanvas.tsx` core entry that owns this variant. Rendering follows the authored lazy `SignalParticles` export in `NeuformBatchEffects.tsx`, its authored adapter, and the exact `signal-particles.html` canonical source. No renderer, shader, animation, source HTML, or original component was redrawn or edited. `PredictiveArcCollection.tsx` and the other registered variant files are retained for provenance; unused collection variants are not entry points for this background.

The source JSON omits HTML imports for unrelated effects referenced by the shared batch module. Those dependency strings were obtained from the official `@designcodeio/threeui@1.2.0` npm distribution; their filenames and SHA-256 values are in `support-manifest.json`. The shared stylesheet's Fragment Mono font is from the official ThreeUI GitHub repository with a recorded hash. MIT and font license files are retained. External URLs inside the canonical source remain unchanged. At build time only the selected variant’s four script URLs are mapped to locally served copies of GSAP 3.12.2, ScrollTrigger 3.12.2, Iconify 1.0.7 and Tailwind 3.4.17. `vendor/runtime/manifest.json` records original URLs, resolved versions and SHA-256 values, all verified before building; the scripts retain their original license notices. This prevents a failed public CDN connection from stopping the particle initializer. Styles and image URLs remain as authored. The selected variant itself uses Canvas 2D; the registered alternate WebGL and Three.js variants remain preserved but inactive.

## Build and integration

```sh
cd frontend/background
npm ci --ignore-scripts
npm run build
```

The pinned React 18.3.1 + esbuild build produces `api_test_tool/static/signal-background/`. Generated assets are committed so Python deployments require no Node runtime. Do not edit generated JavaScript. `build-manifest.json` records the registered source hashes and output sizes.

`frame.html` hosts the small React scene locally. It is not a remote ThreeUI documentation/preview embed. This frame hosts the authored sandboxed source document without changing the workbench's restrictive CSP. Animation script dependencies are served from this application so they do not require client access to public CDNs. Its own meta CSP allows only the authored CDN endpoints; it contains no project data or credentials. The source document keeps its original `sandbox="allow-scripts"` isolation. The host frame is hidden from accessibility navigation, non-focusable, fixed to the viewport and ignores pointer events. Existing controls and dialogs remain above it.

`api_test_tool/static/signal-theme.css` only styles the host background, sidebar/header and text over the dark field. Business panels retain their current styling, and generated historical reports are unchanged.

## Verification

- All 16 registered SHA-256 values match the supplied manifest.
- Build completes with the raw HTML imports, lazy chunk, stylesheet and font resolved.
- Browser rendering checked at desktop size and 390 × 844; the original animated particle field fills the viewport and resizes.
- API management and its configuration dialog open and close; the background intercepts no clicks.
- The example document loads and imports successfully, creating a local preview session with four parsed endpoints.
- No browser runtime errors. The mirrored original Tailwind runtime emits its standard production-use warning.
- No model API calls are made by this background or these checks.
