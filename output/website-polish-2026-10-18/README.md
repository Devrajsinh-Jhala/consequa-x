# Website spacing and real-package walkthrough

Published 18 October 2026. The public landing page keeps the established dark
design and tightens the label/icon spacing across hero, navigation and other
calls to action. Controls preserve usable touch heights. Mobile history can be
expanded, and scenario controls support arrow/Home/End keyboard selection.

The new, user-triggered 23-second GIF contains six browser screenshots of an
actual Consequa-X HTML report, with no replacement interface drawn into frames.
The example is synthetic timeout-after-commit data, not a live payment or model
session. The exact HTML can be opened or downloaded. Pause restores the poster;
no-script users retain the poster and direct links. Intrinsic image dimensions
reserve layout space and the media loads lazily.

The report was also generated in an isolated install of the sealed 1.1.0 wheel;
its bytes match the captured output. `package-demo-provenance.json` records the
wheel, HTML, screenshot and media hashes. This is an output walkthrough, not a
continuous screen recording of package installation.

Browser checks covered 320px, 390px, tablet and desktop layouts with no page
horizontal overflow, menu/Escape, the three inspector meanings, and GIF
play/pause. Reduced-motion CSS and its change listener were inspected; an OS
preference was not emulated. `browser-qa.json` and screenshots retain evidence.
`static-checks.json` binds the 24 public files, six HTML pages and 91 local
references. The quickstart archive retains its four allowlisted public files.

Site version 4 was published at
https://consequa-x.brawny-deer-5658.chatgpt.site from the isolated Site source
commit `550ea3638f4bee8c49348cf46e4c34fe3b6f9df4`.
`publication.json` records the native successful deployment. Anonymous HTTP
checks are retained separately in `public-checks.json`; any explicitly recorded
hosting challenge insertion is distinguished from authored HTML bytes.

The root Render Blueprint and website README prepare a site-only mirror. Render
account connection and actual Render deployment remain outstanding. Private
research records, study logs and the supplied review are excluded from the
public assets. GitHub Actions remain disabled; this work used no Actions.
