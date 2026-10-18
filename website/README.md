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
- Left/right arrows, Home, and End select scenarios while keeping focus on the
  selected control. Scenario, copy, navigation, and motion controls have touch
  targets of at least 44 pixels.
- Button labels and their icons use compact, consistent gaps. Their width follows
  their content; mobile navigation keeps its CTA arrow beside the label.
- The actual-package walkthrough near the quickstart starts with a still image.
  Its play control swaps in the GIF; pause restores the poster. A reduced-motion
  preference change also pauses it. With JavaScript disabled the poster and a
  direct animation link remain available. Visitors can also open the report or
  download a ZIP containing the original offline HTML. These are generated report
  screenshots from synthetic data, not a recording of a live payment or model run.
- On small screens, captured history stays available through a labeled expand
  button. Without JavaScript the full history remains visible. Resizing restores
  the full desktop history, and the evidence graph keeps aligned node centers.
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
shared `?v=20261018-ui4` cache version. Keep references consistent when updating
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

## Render deployment

The repository-root [render.yaml](../render.yaml) prepares a second static host.
It does not create a Render service. No Render deployment or Render URL has been
verified as of 18 October 2026; the existing public Site remains available.

Use a **site-only repository** for this deployment. Copy `render.yaml` and only
the reviewed files under `website/dist/`, retaining that directory structure.
Do not mirror the private research repository, its history, `website/.openai/`,
study captures, PDFs, review files, package-release archives, or credentials.
The publish directory controls which files visitors receive; it does not limit
the repository access granted to a hosting provider. Keep the main repository
private and grant Render access only to the site-only repository.

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
website/dist/assets/package-demo.gif
website/dist/assets/package-demo-poster.png
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

Review changes to this list before exporting a later version. In particular,
`quickstart.zip` contains only the public README, MIT license, and two synthetic
examples; it is not a research artifact download. Preserve the three font
licenses when copying assets.

`assets/sample-report.zip` contains exactly `my-report.html`, the unmodified
self-contained package report with SHA-256
`52c320078c79e5a071a15c051e024c3e541d86dfda6cbbd3685711a8b81492e7`.
Use this ZIP for the offline download: the public Site host can append a browser
challenge script to served HTML, including the browser preview of the report.
The ZIP preserves the original package bytes when extracted. It uses fixed ZIP
metadata and contains synthetic example data only.

1. Connect the intended Render account and the site-only Git repository.
2. Create a Blueprint from that repository and select its root `render.yaml`.
3. Confirm that the resource is a static site, root directory is `website`,
   build command is `true`, and publish directory is `dist`. No frontend build,
   secret, environment variable, database, server, or paid compute plan is needed.
4. Confirm that automatic deploys are **Off** before creating the service. The
   initial creation still performs the first deployment. Later releases use a
   deliberate manual deploy after the site-only snapshot has been reviewed.
5. After Render reports success, record its returned URL and deployed commit.
   Check the five pages, three inspector scenarios, mobile navigation, fonts,
   copy feedback, and the public quickstart download on that URL.

Render hosting does not use GitHub Actions. Leave Actions disabled and do not
select “After CI Checks Pass” as the deployment trigger. The Blueprint uses
`autoDeployTrigger: "off"` and omits compute-plan and region settings for the
static CDN resource. It also omits an SPA rewrite: documentation pages are real
HTML files, and unknown paths should retain their normal not-found response.

The existing sitemap and canonical links identify the current public Site.
Treat Render as a mirror until a primary domain is chosen; review those links
before changing the canonical host. Do not replace them with a guessed Render
subdomain.

Configuration checked against Render's official [Blueprint reference](https://render.com/docs/blueprint-spec)
and [monorepo support](https://render.com/docs/monorepo-support), accessed
18 October 2026. `rootDir` makes the build command and publish directory relative
to `website/`; automatic deployment is disabled independently of GitHub checks.
