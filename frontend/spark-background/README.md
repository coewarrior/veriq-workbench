# ThreeUI SparkBadge workspace background

The three registered files come verbatim from
https://threeui.com/source-code/spark-badge.json. The complete JSON bundle is
retained in vendor/threeui/source-bundle.json. Every build verifies both the
registered hashes and the exact bytes against the user's pinned revision.

Scene.tsx imports SparkBadge and the registered shared stylesheet through the
local @designcodeio/threeui package. It selects the badge variant with speed,
particleAmount, rainAmount, turbulence and spread all set to 1.00. Only the
supported sourceUrl prop is set to the application's static asset URL; the
component, animation, resizing and adaptive load governor are unchanged.
The local wordmark.mjs adaptation replaces only the carved letter paths with
VERIQ at build time, retaining their emission weights and centred placement.
The remaining Canvas 2D scene stays byte-for-byte identical.

The local frame hosts React and the original sandboxed scene, not a ThreeUI
documentation or preview page. No public CDN is needed at runtime. The shared
stylesheet's original font and licenses are reused from the existing verified
ThreeUI vendor directory. Outputs include the byte-exact spark-badge.html and
the branded veriq-badge.html used by the workspace. The manifest records the
original hashes separately from the branded scene's hash.

The workbench mounts a single fixed, non-focusable, pointer-transparent
background frame below the unchanged workspace controls and modal dialogs.
The component keeps its authored visibility lifecycle. Other application
backgrounds (login and home) are not replaced.

Build:

    cd frontend/spark-background
    npm ci --ignore-scripts --no-audit --no-fund
    npm run build

Generated assets are committed under api_test_tool/static/spark-background
so the Python application needs no Node runtime. Do not edit generated assets.
