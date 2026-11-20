# Liquid Glass CSS attribution

Source: https://github.com/GANSGX/liquid-glass-css
Git tree: `f4b397fcaa5cf32e9a7a501391861357f48542ef`
License: MIT (see LICENSE).
Upstream stylesheet retained byte-for-byte as upstream.css, SHA-256 `923caeb32a2279beebaf0693051f70aec6c44666e49111e77ab1d1f3ecff7d23`.

The application loads ../../workspace-glass.css, an adaptation of the base glass surface and masked edge highlights. It scopes selectors to existing workspace cards, tunes the dark tint, preserves form layout, adds keyboard focus and reduced-transparency/no-backdrop fallbacks. It does not load upstream global body styles or demo helpers. Assets are served locally with no CDN or runtime dependency.

Also evaluated https://github.com/dashersw/liquid-glass-js (MIT). Its html2canvas page sampling and per-container WebGL loops were not selected for these dynamically updated form/report surfaces. This implementation uses native backdrop blur and specular edge gradients, not optical WebGL refraction or Apple's native renderer.

The shared-glass.css adaptation extends the same material to navigation, dialogs, API/PingCode management, help and reports. Login/register do not load it. Reports embed it for offline use; screen-only rules preserve print styling.
