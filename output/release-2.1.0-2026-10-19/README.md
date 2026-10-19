# Consequa-X 2.1.0 release record

Additive feature release with the roadmap features 2.0.0 left out: verifier
composition (`all_of`, `any_of`, `CompositeVerifier`, several readbacks per
verification), optional OpenAI Agents SDK, LangChain and Claude Agent SDK
integrations, and OpenTelemetry export and import. Trace schema `1.0` and the
2.0 API are unchanged. See the [changelog](../../CHANGELOG.md). Built from
source revision `a19e6c89e07e2123bd5256eb786bbfb7ccbe0448`.

Published to PyPI on 19 October 2026 (11:21 UTC) on the maintainer's
instruction, with the public docs/support gate recorded as pending until the 2.1
site deploys.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `consequa_x-2.1.0-py3-none-any.whl` | 215,066 | `6cdbe68bf0e4c722f1220987ee7fd9a1d167fdadec48a97f236ec7a1570e3670` |
| `consequa_x-2.1.0.tar.gz` | 647,396 | `fcb98e019c3c40ebcd2c6500732ca770b53a7380cf04786655e482219b4032e7` |

## What was checked

- Full source suite at the release revision: 1,921 passed, 26 skipped, 241
  subtests, 0 failures ([log](source-tests.log)); lint passed. Five of the
  skips are the SDK tests, which ran in the extras environment below.
- Artifact inventory and strict metadata audit: 54 runtime files, 60 wheel
  entries, 217 source-archive files; no required runtime dependency
  ([inventory.json](inventory.json)).
- Installed-wheel checker, which now also exercises an `all_of` contract with
  two readbacks per verification (a lagging part kept `unknown`, then settled),
  a violated part beside a missing readback, `any_of`, the composite report,
  OpenTelemetry export without payloads, restore from a payload export, tool
  spans recorded as actions, `ToolCallCapture`, and the integration modules'
  missing-extra import errors:
  - Windows, official embedded Python 3.11.9 ([windows311.json](windows311.json));
  - Windows, fresh Python 3.12.10 venv ([windows312.json](windows312.json));
  - Alpine Linux 3.24.2, Python 3.14.8, kernel 6.18.52-0-virt, in a local QEMU
    guest with a fresh venv ([linux.json](linux.json)). The guest also ran the
    SQLite agent-loop example in all three modes and the `consequa-x` console
    script ([log](linux-guest.log)).
- Framework extras: the same wheel installed into a Windows Python 3.12.10 venv
  with openai-agents 0.24.0, langchain-core 1.6.12, claude-agent-sdk 0.2.168 and
  opentelemetry-api/sdk 1.45.1; the integration, OpenTelemetry and composite
  tests ran from a folder outside the checkout against the installed package:
  37 passed, none skipped ([extras312.json](extras312.json),
  [log](extras312.log)). Each SDK was driven offline: the Agents SDK's
  `ScriptedModel` in a real `Runner` loop, real LangChain tools with callbacks,
  the Claude Agent SDK's hook protocol through a scripted transport, and spans
  through the OpenTelemetry SDK's in-memory exporter.
- Source distribution on Windows Python 3.12.10: built and installed; ran the
  demo, `summarize`, the SQLite example in all three modes, migration of a
  trace written by 1.2.0, an `otel-export`/`otel-import` round trip and a
  composite `verify` from two readback files ([sdist312.json](sdist312.json)).
- Browser review at desktop and mobile widths: a composite report (default, and
  `--include-details` with keys redacted) rendered by the installed wheel has no
  page overflow, scripts, external references or leaked values; the homepage
  shows v2.1, the framework section and `consequa-x==2.1.0` without overflow;
  the docs page shows version 2.1 ([browser-qa.json](browser-qa.json),
  [report](report-composite-desktop.png), [homepage](homepage-stack-mobile.png)).
  The review found that report table cells collapsed to one character per line
  on phones, a defect present since 2.0. It was fixed in `a19e6c8` and every
  check above ran on the rebuilt artifacts; the first build's receipts were
  set aside.
- After upload: PyPI serves both files with the reviewed sizes and hashes, and a
  fresh no-cache install from PyPI on Windows Python 3.12.10 passed the
  installed-wheel checker, including the 2.1 feature checks
  ([registry312.json](registry312.json), [publication.json](publication.json),
  [upload log](publication-upload.log)). The wheel download that followed the
  install first reached an index node that did not list 2.1.0 yet; the retry
  passed.

## Pending and limits

- Public docs/support gate: pending at upload, met after publication. The 2.1
  site went live from the `consequa-x-site` mirror (`f006f56`, byte-identical to
  this repository's `main` at `b57f9a3`), and private vulnerability reporting is
  enabled ([site-publication.json](site-publication.json)). Render still deploys
  from that mirror.
- macOS has never been tested. Linux coverage is one emulated Alpine guest; the
  framework SDKs were installed only in the Windows extras environment.
- The integrations were tested against one version of each SDK, offline: no
  live model, MCP server, OpenTelemetry collector or tracing backend.
- Retained 1.x study outputs under `output/` are unchanged and bound to their
  recorded revisions.

Gate states are in [checks.json](checks.json). GitHub Actions was not used.
