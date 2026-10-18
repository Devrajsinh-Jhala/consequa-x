# Consequa-X 1.2.0 release record

Additive feature release: `TraceRecorder`, tool-call capture (`attempt()`,
`call()`, `capture_tool`, `call_mcp_tool`), `RecordVerifier` and the SQLite
agent-loop example. The 1.x API and schema 0.1 are unchanged. Built from source
revision `2afea71f2b8facf90562564aa8cdfee7168bb945`; the later commit
`1bc1222` changed only `website/dist/index.html` and `website/dist/styles.css`,
which are not in either distribution file.

**Not yet published.** This record holds the pre-publication checks. Publication
needs the maintainer's approval; `publication.json` will be added after upload
and registry verification.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `consequa_x-1.2.0-py3-none-any.whl` | 168,920 | `4cdfb44c6a56e1671e50ee9efddc97816d8742fa388130ffa7d351eee3686438` |
| `consequa_x-1.2.0.tar.gz` | 557,611 | `d47c9b433f746ef5c263487ec668f908538f6485cff7d444649d62e2fde2af43` |

## What was checked

- Full source suite: 1,839 passed, 21 skipped, 240 subtests, 0 failures
  ([log](source-tests.log)); lint passed.
- Artifact inventory and strict metadata audit: 40 runtime files, 46 wheel
  entries, 182 source-archive files ([inventory.json](inventory.json)).
- Installed-wheel checker, which now also exercises the recorder, `attempt()`,
  `capture_tool`, `call()`, `RecordVerifier` and `call_mcp_tool` (with a
  stand-in session) from the installed wheel:
  - Windows, official embedded Python 3.11.9 ([windows311.json](windows311.json));
  - Windows, fresh Python 3.12.10 venv ([windows312.json](windows312.json));
  - Alpine Linux 3.24.2, Python 3.14.8, kernel 6.18.52-0-virt, in a local QEMU
    guest ([linux.json](linux.json), [environment](linux-environment.json)).
    The guest also ran the SQLite agent-loop example in all three modes and the
    `consequa-x` console script ([log](linux-guest.log)).
- Source distribution on Windows Python 3.12.10: built and installed, reproduced
  the published sample report byte for byte, and ran the SQLite example in all
  three modes with the expected results ([sdist312.json](sdist312.json)).
- Report browser review: the renderer is unchanged since 1.1.1. Reports of
  recorder-built traces were checked at desktop and mobile widths: no overflow,
  no scripts or external references, captured values omitted by default
  ([browser-qa.json](browser-qa.json), [desktop](report-desktop.png),
  [mobile](report-mobile.png)).

## Pending and limits

- Public docs/support gate: pending. Private vulnerability reporting is enabled.
  The 1.2.0 site states 1.2.0 as published, so it deploys only after publication
  and the merge to `main`, and Render must serve the site from this repository.
- macOS has never been tested. Linux coverage is one emulated Alpine guest.
- MCP capture was checked with a stand-in session, not a live MCP server.

Gate states are in [checks.json](checks.json). GitHub Actions was not used.
