# Consequa-X 2.0.0 release record

Breaking feature release: trace schema `1.0` (several actions per trace, a
declared time base, keyword-only and read-only records), verifier-owned target
matching and findings, structured diagnoses, migration of 0.1 traces, and new
capture, collection and command-line tools. See the
[changelog](../../CHANGELOG.md) and the
[migration guide](../../docs/migrating-to-2.0.md). Built from source revision
`87463bf290ff1a1da9b270a7b11f48c512549172`.

Published to PyPI on 19 October 2026 (09:46 UTC) on the maintainer's
instruction, with the public docs/support gate recorded as pending until the 2.0
site deploys.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `consequa_x-2.0.0-py3-none-any.whl` | 191,053 | `b9d7a1c6676fc8de84df437acd48feef7a6a77e78fd625cac235cd647844793c` |
| `consequa_x-2.0.0.tar.gz` | 607,605 | `70868f903271f2ae9f9dc7f73fd2bb993e406934b115db89018aa76cdb0c9c45` |

## What was checked

- Full source suite: 1,888 passed, 21 skipped, 241 subtests, 0 failures
  ([log](source-tests.log)); lint passed.
- Artifact inventory and strict metadata audit: 48 runtime files, 54 wheel
  entries, 207 source-archive files ([inventory.json](inventory.json)).
- Installed-wheel checker, which now also exercises a two-action capture with
  readback polling and retry advice, refusal of schema 0.1 and conservative
  migration, `TraceStore`, `summarize` and `compare`:
  - Windows, official embedded Python 3.11.9 ([windows311.json](windows311.json));
  - Windows, fresh Python 3.12.10 venv ([windows312.json](windows312.json));
  - Alpine Linux 3.24.2, Python 3.14.8, kernel 6.18.52-0-virt, in a local QEMU
    guest with a fresh venv ([linux.json](linux.json)). The guest also ran the
    SQLite agent-loop example in all three modes and the `consequa-x` console
    script ([log](linux-guest.log)).
- Source distribution on Windows Python 3.12.10: built and installed; ran the
  demo, `summarize`, the SQLite example in all three modes, and migrated a trace
  written by the released 1.2.0 package, reproducing its 1.x explanation
  ([sdist312.json](sdist312.json)).
- Browser review at desktop and mobile widths: homepage and docs show 2.0.0 with
  no overflow or script errors; reports of a two-action trace, a redacted
  details report and the SQLite example have no overflow, scripts or external
  references, and redacted or omitted values are absent
  ([browser-qa.json](browser-qa.json),
  [report](report-multi-desktop.png), [homepage cards](homepage-cards-mobile.png)).
  The first build had a long diagnosis code overflowing its card; it was fixed
  and every check above ran on the rebuilt artifacts.
- After upload: PyPI serves both files with the reviewed sizes and hashes, and a
  fresh no-cache install from PyPI on Windows Python 3.12.10 passed the
  installed-wheel checker, including the 2.0 feature checks
  ([registry312.json](registry312.json), [publication.json](publication.json),
  [upload log](publication-upload.log)). The first install attempt ran before
  PyPI's index served 2.0.0 to pip; the retry twenty seconds later passed.

## Pending and limits

- Public docs/support gate: pending at upload, met after publication. The 2.0
  site went live from the `consequa-x-site` mirror (`2719334`, byte-identical to
  this repository's `main` at `b1e5bfc`), and private vulnerability reporting is
  enabled ([site-publication.json](site-publication.json)). Render still deploys
  from that mirror.
- macOS has never been tested. Linux coverage is one emulated Alpine guest.
- MCP capture was checked with a stand-in session, not a live MCP server.
- Not in 2.0.0: verifier composition, optional framework integrations and
  OpenTelemetry export (planned for 2.1).
- Retained 1.x study outputs under `output/` are unchanged and bound to their
  recorded revisions.

Gate states are in [checks.json](checks.json). GitHub Actions was not used.
