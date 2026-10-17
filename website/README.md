# Consequa-X public website

`dist/` contains a buildless landing page and public documentation. Serve it as
static files; no package installation or frontend build is required. Authored
pages use no third-party scripts, remote fonts or images, analytics, cookies,
database, or account flow. The hosting CDN can append its browser challenge
script. Offline package report files have no hosting runtime.

The visual direction uses dark graphite panels, lime accents, a large display
headline, a three-panel evidence inspector, and a contrasting light workflow
section. Inline SVG and CSS draw the evidence paths and product illustrations.
The page moves from an interactive synthetic trace to the application boundary,
evidence preservation, disclosure defaults, and a runnable quickstart. The public
documentation, support, security, and changelog pages share the dark theme.

Space Grotesk, Manrope, and JetBrains Mono are self-hosted variable font assets
with system fallbacks and `font-display: swap`. They are distributed under the
SIL Open Font License, Version 1.1; the package's MIT license does not replace
those licenses. Preserve `dist/fonts/*-OFL.txt` with the fonts. The pinned upstream
sources, copyright notices, and checksums are in [font attribution](dist/fonts/README.md).

## Local preview

From the repository root, run `python -m http.server 8787 --directory website/dist`
and open `http://127.0.0.1:8787`. The existing public Site and hosting identity
are recorded in `.openai/hosting.json`; publication uses the Sites workflow.

## Behavior and accessibility

- Navigation links lead to sections and the public documentation pages.
- The mobile menu exposes `aria-expanded`, closes after navigation and on Escape.
- Scenario buttons use `aria-pressed`. The conclusion updates in a polite live
  region while the readback, evidence relationship, and scenario colors update
  together. The three cases distinguish timeout after commit, missing readback,
  and an effect produced by another actor. All content is a hard-coded synthetic
  illustration; changing scenarios performs no framework execution, persistence,
  or external call.
- Copy install uses the Clipboard API on a secure origin. If unavailable, it
  selects the command and announces how to copy it manually.
- The inspector has a pause/resume control. `prefers-reduced-motion` removes animation
  and scrolling motion. Scroll reveals progressively enhance an otherwise fully
  visible document. Every action works with a keyboard.
- Labels accompany colors, focus outlines remain visible, SVG decoration is
  hidden from assistive technology, and print rules remove moving decoration.

The landing inspector is an **illustrative interface**, not a pixel preview of
the package-generated report. The latter intentionally works without JavaScript.
The illustration assumes an explicit action-linked target matcher; offline
package reports leave assessment alignment unassessable and execute no verifier,
matcher, action, or replay. Qualified provenance is separate from causal
necessity. Scenario fields are rendered with text nodes; no scenario content
enters an HTML parser.

## Release status

Version 1.1.0 is published on PyPI, and the installation command targets
`consequa-x==1.1.0`. The homepage release badge and quickstart describe that
published release. The UI redesign does not change the Python package or its
offline report renderer. Do not describe unverified platform support or present
the browser illustration as a live application execution.

`scripts/build_public_docs.py` regenerates the four public documentation pages,
`docs.css`, the explicitly allowlisted synthetic examples, and `quickstart.zip`.
Run it with `--published` to retain the published release status and pass the
existing successful installed-wheel receipts through repeatable
`--platform-receipt` arguments to retain the actual platform validation table.
The downloadable archive contains only its README, MIT license, and two public
Python examples. Research captures and private repository data are not website
inputs. GitHub Actions remains disabled.

HTML references to `styles.css`, `app.js`, `docs.css`, and the favicon use a
shared `?v=20261018-ui2` cache version. Keep references consistent when updating
authored assets; font binaries have stable local filenames and pinned checksums.

## Verification

Run the local Node syntax check on `dist/app.js`. Check all internal links after
the documentation pages are generated. Browser review should include desktop,
390-pixel mobile, keyboard navigation, copy feedback, all three scenarios,
pause/resume, reduced motion, no horizontal overflow, and requests limited to
same-origin static assets. Confirm that unknown evidence does not acquire a
success icon or qualified provenance, and that the other-actor case retains its
distinct state and origin. Verify all three self-hosted fonts load, their license
and attribution files remain available, public download links work, and docs
tables stay scrollable on small screens. Do not infer a package runtime test
result from website checks.

The main research repository stays private. Public package users should follow
the documentation and support links, rather than links to private GitHub issues.
