# Original offline-report delivery

Follow-up to the spacing and real-package walkthrough revision on 18 October
2026. The host inserts a security challenge script into served HTML, including
the browser preview of the synthetic sample report. The offline download now
uses a deterministic ZIP so those hosting additions cannot alter the original
report inside it.

The ZIP contains exactly `my-report.html`. Its 22,674 bytes match the report
generated from the released 1.1.0 wheel, SHA-256
`52c320078c79e5a071a15c051e024c3e541d86dfda6cbbd3685711a8b81492e7`.
The original HTML has no scripts. The ZIP SHA-256 is
`dc52433357c1a392485cdb6869dd4a958c06b4f1cc0681466129f167c254edc1`.

The page labels the ZIP download and retains the online browser preview and
user-triggered GIF. CSS, JavaScript and the recorded media are unchanged.
Public Site version 5 contains 25 authored assets; the archive includes those
assets and the hosting manifest. Publication, static checks and anonymous
HTTP byte checks are recorded in this directory. Earlier version-4 proof files
remain unchanged.

The current sanitized Render bundle is
`output/render-site-2026-10-18-v2/consequa-x-render-site.zip`, with 26 approved
files including the Render config. It is prepared, not deployed to Render.
The private repository, research records and credentials are excluded.
GitHub Actions remain disabled.
