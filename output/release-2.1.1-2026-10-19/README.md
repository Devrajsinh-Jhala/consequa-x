# ConseqaX 2.1.1 release record

Maintenance release. The API and trace schema `1.0` are unchanged. The project's
name is written ConseqaX (the package, command and import names stay
`consequa-x` and `consequa_x`). Python 3.13, 3.14 and 3.15 are tested and
declared, each framework integration was run with a real model, and the
two-part outcome example ships in the source archive. See the
[changelog](../../CHANGELOG.md). Built from source revision
`b73ecd00fc9b4b8b3f9b8182aa8ed652419d7e54`.

Published to PyPI on 19 October 2026 (15:15 UTC) on the maintainer's
instruction. PyPI serves both files with the reviewed sizes and hashes, the
2.1.1 metadata lists Python 3.11 to 3.15 and the README headed ConseqaX, and a
fresh no-cache install from PyPI on Windows Python 3.12.10 passed the
installed-wheel checker ([registry312.json](registry312.json),
[publication.json](publication.json), [upload log](publication-upload.log)).

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `consequa_x-2.1.1-py3-none-any.whl` | 215,139 | `c86c02aacac53d51bd4335238c4f44b96098db9af354662b23722fab60ed3b98` |
| `consequa_x-2.1.1.tar.gz` | 676,766 | `9841f34842c89bbbdffa6776bbc5baf32e2288f25a35cfc1ad1e3f665021fa69` |

## What was checked

- Full source suite at the release revision on Python 3.12: 1,952 passed, 27
  skipped, 241 subtests, 0 failures ([log](source-tests.log)); lint passed. The
  full suite also ran on official Python 3.13.16, 3.14.8 and 3.15.0 at `4f2cf80`
  (before the version bump): one failure each, the demo-data comparison, which
  raced a regeneration of that data during the run and passed on rerun
  ([3.13](source-tests-py313.log), [3.14](source-tests-py314.log),
  [3.15](source-tests-py315.log)).
- Artifact inventory and strict metadata audit: 54 runtime files, 60 wheel
  entries, 223 source-archive files ([inventory.json](inventory.json)).
- Installed-wheel checker, including the 2.0 and 2.1 feature checks:
  - Windows, official embedded Python 3.11.9, 3.13.16, 3.14.8 and 3.15.0
    (python.org builds, the last three verified against their release managers'
    Sigstore signatures) ([3.11](windows311.json), [3.13](windows313.json),
    [3.14](windows314.json), [3.15](windows315.json));
  - Windows, fresh Python 3.12.10 venv ([windows312.json](windows312.json));
  - Alpine Linux 3.24.2, Python 3.14.8, in a local QEMU guest with a fresh venv
    ([linux.json](linux.json)). The guest also ran the SQLite agent-loop example
    in all three modes, the two-part example in both modes, and the
    `consequa-x` console script ([log](linux-guest.log)).
- Framework extras on the installed wheel: the integration, OpenTelemetry and
  composite tests with openai-agents 0.24.0, langchain-core 1.6.12,
  claude-agent-sdk 0.2.168 and opentelemetry 1.45.1, from a folder outside the
  checkout: 37 passed, none skipped ([extras312.json](extras312.json)).
- Live runs on the installed wheel ([live-integrations.json](live-integrations.json)):
  each integration in a real agent loop with a real model, asked to refund an
  order through a tool that commits and then times out. The OpenAI Agents SDK
  and LangChain used a local qwen3 4B model through Ollama; the Claude Agent SDK
  used Claude Haiku through the local Claude Code login. In all three, the
  recorded attempts matched the tool calls that ran, readback showed the refund,
  and the agent's report of failure was found contradicted.
- Source distribution on Windows Python 3.12.10: installed and ran the demo,
  `summarize`, both examples, migration of a 1.2.0 trace, the OpenTelemetry
  commands and a composite verify ([sdist312.json](sdist312.json)).
- Browser review at desktop and mobile widths: the composite report rendered
  by the installed wheel, the homepage and the docs page show ConseqaX and no
  previous spelling, with no overflow, scripts, external references or leaked
  values ([browser-qa.json](browser-qa.json),
  [report](report-composite-desktop.png), [homepage](homepage-stack-mobile.png)).

## Pending and limits

- Public docs/support gate: pending at upload, met after publication. The 2.1.1
  site went live from the `consequa-x-site` mirror (`ebe3390`, byte-identical to
  this repository's `main` at `a4a0c19`), and private vulnerability reporting is
  enabled. GitHub releases now exist for every version from 1.1.0 to 2.1.1,
  with 2.1.1 marked latest ([site-publication.json](site-publication.json)).
- macOS has never been tested. Linux coverage is one emulated Alpine guest.
- One live run per framework, with one model each, shows the wiring works; it
  does not cover every model or SDK release. No MCP server, OpenTelemetry
  collector or tracing backend was used.

Gate states are in [checks.json](checks.json). GitHub Actions was not used.
