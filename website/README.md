# Consequa-X public website

`dist/` contains a buildless landing page and public documentation. Authored assets
use no third-party scripts, fonts, remote images, analytics, cookies, database,
account flow, or runtime dependencies. The hosting CDN can append its browser
challenge script; offline package report files have no hosting runtime. Serve
`dist/` as static files. The owning
task manages Sites registration, publication and the hosting manifest.

The visual direction uses warm paper, dark ink, teal and lime, with system sans,
Georgia and monospace fonts. The hero diagram is inline SVG and CSS; no bitmap
or remote media is required. The narrative proceeds from the problem to the
capture/readback/explanation boundary, synthetic evidence explorer, disclosure
defaults and a runnable quickstart.

## Local preview

From the repository root, run `python -m http.server 8787 --directory website/dist`
and open `http://127.0.0.1:8787`. A static server is sufficient; no build is
required. The live hosted Site is managed separately by the parent task.

## Behavior and accessibility

- Navigation links lead to sections and the public documentation pages.
- The mobile menu exposes `aria-expanded`, closes after navigation and on Escape.
- Scenario buttons use `aria-pressed`; the conclusion updates in a polite live
  region. All scenario content is hard-coded synthetic illustration and performs
  no framework execution, persistence or network access.
- Copy install uses the Clipboard API on a secure origin. If unavailable, it
  selects the command and announces how to copy it manually.
- The hero has a pause/resume control. `prefers-reduced-motion` removes animation
  and scrolling motion. Scroll reveals progressively enhance an otherwise fully
  visible document. Every action works with a keyboard.
- Labels accompany colors, focus outlines remain visible, SVG decoration is
  hidden from assistive technology, and print rules remove moving decoration.

The landing explorer is an **illustrative interface**, not a pixel preview of
the package-generated report. The latter intentionally works without JavaScript.
The graph distinguishes qualified provenance from causal necessity. Captured
fields are rendered with text nodes; no scenario content enters an HTML parser.

## Release status

Until the release gate passes, the homepage labels version 1.1 as preparing and
states that the stable 1.0 package remains available. On publication, update
`[data-release-status]` and `[data-release-note]` in `dist/index.html`. The install
command already targets `consequa-x==1.1.0`. Do not describe unverified platform
support or claim the illustrative browser demo is a live execution.

## Verification

Run the local Node syntax check on `dist/app.js`. Check all internal links after
the documentation pages are generated. Browser review should include desktop,
390-pixel mobile, keyboard navigation, copy feedback, all three scenarios,
pause/resume, reduced motion, no horizontal overflow, and requests limited to
same-origin static assets. The homepage requires only `index.html`, `styles.css`,
`app.js`, and `favicon.svg`.

The main research repository stays private. Public package users should follow
the documentation and support links, rather than links to private GitHub issues.
