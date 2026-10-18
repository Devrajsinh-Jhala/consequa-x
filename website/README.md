# Consequa-X public website

`dist/` contains a buildless landing page and public documentation. Serve it as
static files; no package installation or frontend build is required. Authored
pages use no third-party scripts, remote fonts or images, analytics, cookies,
database, or account flow. The hosting CDN can append its browser challenge
script. Offline package report files have no hosting runtime.

The visual direction keeps the dark graphite panels, lime accents and display
headline. The homepage moves from a real-trace evidence inspector, through the
three-step API in a contrasting light section, to a live terminal-and-report
demo, the evidence-preservation and disclosure capabilities, and a runnable
quickstart. The public documentation, support, security, and changelog pages
share the base stylesheet and dark theme.

Space Grotesk, Manrope, and JetBrains Mono are self-hosted variable font assets
with system fallbacks and `font-display: swap`. They are distributed under the
SIL Open Font License, Version 1.1; the package's MIT license does not replace
those licenses. Preserve `dist/fonts/*-OFL.txt` with the fonts. The pinned upstream
sources, copyright notices, and checksums are in [font attribution](dist/fonts/README.md).

## Local preview

From the repository root, run `python -m http.server 8787 --directory website/dist`
and open `http://127.0.0.1:8787`. The original host's identity is recorded in `.openai/hosting.json`; that host is
no longer updated.
The report window in the live demo needs an HTTP origin; it cannot script a
`file://` page.

## Demo data comes from real package runs

`dist/assets/demo-data.js` is generated, never hand-edited. Regenerate or check it
with the package installed:

```sh
python scripts/build_site_demo.py
python scripts/build_site_demo.py --check
```

The script runs `consequa-x --version`, `consequa-x demo --output my-demo` and
`consequa-x report my-demo/traces/episode_01.json --output my-report.html` in a
new temporary directory and records their standard output. Printed absolute
paths are shown relative to that directory; nothing else is edited. It refuses to
write if the rendered report differs from `dist/assets/sample-report.html` by a
single byte. For the inspector it loads four demo traces (`timeout_after_commit`,
`delayed_visibility`, `external_actor`, `delayed_reconciled`), runs `explain()` on
each, requires the result to equal the CLI's exported explanation and printed
diagnosis, and extracts the captured timeline, contract window, readback
watermarks and the package's own evidence-graph nodes and links. Captured-order
links and context events are omitted from the drawn graph; the page states the
full node count. `tests/test_site_demo.py` fails if the committed data or the
homepage results table drifts from a fresh run.

## Behavior and accessibility

- The evidence inspector replays the recorded milliseconds of each trace. History
  entries, readback watermarks, effect markers, graph nodes and links appear when
  the playhead reaches their recorded time; the verdict stays pending until a
  verification is captured, and alignment and diagnoses appear only once every
  captured verification is in view. Playback compresses the gaps between times;
  the clock always shows the recorded value. It plays once when scrolled into
  view, then rests on the final state.
- Inspector tabs follow the ARIA tab pattern with arrow, Home and End keys. Play,
  replay and a scrubber control playback. The verdict is a polite live region.
  Below the inspector, a table lists all four `explain()` results without
  JavaScript.
- The live demo types the recorded commands, streams their output, then opens the
  exact report those commands wrote in a sandboxed same-origin frame
  (`sandbox="allow-same-origin"`, no scripts). The report renders at desktop
  width and scales to fit on wide screens. A short tour scrolls its summary,
  timeline, readback and graph; scrolling the report yourself ends the tour.
  Section buttons jump directly. Pause and replay are always available, and a
  screen-reader transcript holds the complete session. Without JavaScript the
  report frame is still visible and usable.
- The mobile menu exposes `aria-expanded` and closes after navigation, on Escape
  and on an outside click. Interactive targets are at least 40 pixels.
- Copy install uses the Clipboard API on a secure origin. If unavailable, it
  selects the command and announces how to copy it manually.
- Motion uses one easing family and animates only opacity and transforms. The hero
  entrance is CSS-only, so it never waits for or flashes before the script.
  `prefers-reduced-motion` removes all animation: the inspector shows final
  states and the demo shows the complete session without typing or touring.
- Labels accompany colors, focus outlines remain visible, decorative SVG is
  hidden from assistive technology, and print rules drop the interactive demo.

The inspector and demo display recorded package output; they run no action,
verifier, target matcher, model or replay in the browser. Offline package
reports leave assessment alignment unassessable; the inspector shows the
alignment that `explain()` computed for each trace with its built-in refund
matching. Provider-origin links are qualified provenance, not causal necessity.
All captured strings are inserted as text nodes; no data enters an HTML parser.

## Release status

Version 1.1.0 is published on PyPI, and the installation command targets
`consequa-x==1.1.0`. The homepage release badge and quickstart describe that
published release. The UI redesign does not change the Python package or its
offline report renderer. Do not describe unverified platform support or present
recorded output as a live application execution.

`scripts/build_public_docs.py` regenerates the four public documentation pages
from `docs/quickstart.md`, `SECURITY.md`, `docs/release-notes.md` and the README,
`docs.css`, the explicitly allowlisted synthetic examples, and `quickstart.zip`.
Run it with `--published` to retain the published release status and pass the
existing successful installed-wheel receipts through repeatable
`--platform-receipt` arguments to retain the actual platform validation table.
The downloadable archive contains only its README, MIT license, and two public
Python examples. Research captures and study data are not website inputs. GitHub Actions remains disabled.

HTML references to `styles.css`, `app.js`, `docs.css`, `assets/demo-data.js` and
the favicon use a shared `?v=20261018-ui5` cache version. Keep references
consistent when updating authored assets; font binaries have stable local
filenames and pinned checksums.

## Verification

Run `node --check dist/app.js`, `python scripts/build_site_demo.py --check` and
`python -m pytest tests/test_site_demo.py tests/test_render_site_export.py`.
Browser review should include desktop, 390-pixel mobile, keyboard navigation,
all four inspector traces at their final and intermediate states, the full demo
sequence, taking over the report scroll, reduced motion, copy feedback, no
horizontal page overflow, and requests limited to same-origin static assets.
Confirm that unknown evidence never acquires a success state, that the
`external_actor` graph has no provider-origin link from the dispatch, and that
`delayed_reconciled` retains its earlier unknown verification. Verify all three
self-hosted fonts load, their license files remain available, and public
download links work. Hidden browser tabs throttle animation frames; judge timing
in a visible or headless browser. Do not infer a package runtime test result
from website checks.

Questions, bug reports and private vulnerability reports go to this public
repository; the website's support and security pages link there.

## Render deployment

The repository-root [render.yaml](../render.yaml) defines the static site served
at <https://consequa-x.onrender.com>, which is the canonical public address: the
sitemap, robots file and package metadata name it. Render builds nothing
(`buildCommand: "true"`), publishes `website/dist`, and deploys automatically on
each commit (`autoDeployTrigger: "commit"`). Because `rootDir` is `website`,
Render's monorepo handling skips automatic deploys for commits that change only
files outside that directory, such as the package or the paper. The original
host at `consequa-x.brawny-deer-5658.chatgpt.site` is no longer updated.

The service previously deployed from the site-only repository
`Devrajsinh-Jhala/consequa-x-site`, created while this repository was private.
After this repository became public, the service should be connected to it
instead; the site-only repository is then redundant.

Every file under `website/dist/` is public. `scripts/export_render_site.py`
remains a reviewed allowlist check: it refuses unlisted files, external
resources and changed report bytes.

The current public asset allowlist is:

```text
render.yaml
website/dist/index.html
website/dist/docs.html
website/dist/support.html
website/dist/security.html
website/dist/changelog.html
website/dist/styles.css
website/dist/docs.css
website/dist/app.js
website/dist/favicon.svg
website/dist/robots.txt
website/dist/sitemap.xml
website/dist/quickstart.zip
website/dist/assets/demo-data.js
website/dist/assets/sample-report.html
website/dist/assets/sample-report.zip
website/dist/examples/artifact_delivery.py
website/dist/examples/report_quickstart.py
website/dist/fonts/README.md
website/dist/fonts/SpaceGrotesk-Variable.ttf
website/dist/fonts/SpaceGrotesk-OFL.txt
website/dist/fonts/Manrope-Variable.ttf
website/dist/fonts/Manrope-OFL.txt
website/dist/fonts/JetBrainsMono-Variable.ttf
website/dist/fonts/JetBrainsMono-OFL.txt
```

Review changes to this list before publishing a later version. In particular,
`quickstart.zip` contains only the public README, MIT license, and two synthetic
examples; it is not a research artifact download. `assets/demo-data.js` contains
only recorded output from the synthetic demo. Preserve the three font licenses
when copying assets.

`assets/sample-report.zip` contains exactly `my-report.html`, the unmodified
self-contained package report with SHA-256
`52c320078c79e5a071a15c051e024c3e541d86dfda6cbbd3685711a8b81492e7`.
Use this ZIP for the offline download: the public Site host can append a browser
challenge script to served HTML, including the browser preview of the report.
The ZIP preserves the original package bytes when extracted. It uses fixed ZIP
metadata and contains synthetic example data only.

1. Connect the intended Render account and this Git repository.
2. Create a Blueprint from that repository and select its root `render.yaml`.
3. Confirm that the resource is a static site, root directory is `website`,
   build command is `true`, and publish directory is `dist`. No frontend build,
   secret, environment variable, database, server, or paid compute plan is needed.
4. Automatic deploys are **On commit**: a push that changes `website/` deploys.
   Review website changes before pushing them, because the push is the release.
   If the service predates this setting, enable On Commit in its Render settings
   or sync the Blueprint once.
5. After Render reports success, record its returned URL and deployed commit.
   Check the five pages, the four inspector traces, the live demo, mobile
   navigation, fonts, copy feedback, and the public quickstart download on that URL.

Render hosting does not use GitHub Actions. Leave Actions disabled and do not
select “After CI Checks Pass” as the deployment trigger. The Blueprint uses
`autoDeployTrigger: "commit"` and omits compute-plan and region settings for the
static CDN resource. It also omits an SPA rewrite: documentation pages are real
HTML files, and unknown paths should retain their normal not-found response.

The sitemap and robots file name the Render address as the canonical host.
Review them, the package metadata and the README together if a custom domain
is added later.

Configuration checked against Render's official [Blueprint reference](https://render.com/docs/blueprint-spec)
and [monorepo support](https://render.com/docs/monorepo-support), accessed
18 October 2026. `rootDir` makes the build command and publish directory relative
to `website/`; the commit trigger deploys without waiting for GitHub checks.
