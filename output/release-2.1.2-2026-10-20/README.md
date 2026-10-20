# ConseqaX 2.1.2 release record

Maintenance release. The API, exported records and trace schema `1.0` are
unchanged. `ActionExplanation.diagnosis`, the one-line display label, is now
always the diagnosis codes joined with ` / `: `consequa-x demo` prints
`ASSESSMENT_DIVERGENCE / ACKNOWLEDGEMENT_EFFECT_DIVERGENCE` for the
timeout-after-commit case instead of the 1.x label `BELIEF / RESPONSE
DIVERGENCE`. Found by an outside audit of the homepage terminal. See the
[changelog](../../CHANGELOG.md). Built from source revision
`064127ff120abae543abfe69f77e44b03f3b928e`.

**Not yet published.** This record holds the pre-publication checks.
`publication.json` will be added after upload and registry verification.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `consequa_x-2.1.2-py3-none-any.whl` | 215,119 | `877143419920a556cd2498925fbd31d7204b5dcac9605de526235380b9b70ba0` |
| `consequa_x-2.1.2.tar.gz` | 731,211 | `993553008642e7d61d0d023b092fd979e1d42d706ec67db3ce89256222e6085c` |

## What was checked

- Full source suite at the release revision on Python 3.12: 2,091 passed, 27
  skipped, 241 subtests, 0 failures ([log](source-tests.log)); lint passed.
  The suite includes a new test that `consequa-x demo` prints each scenario's
  codes and never the 1.x label.
- Artifact inventory and strict metadata audit: 54 runtime files, 60 wheel
  entries, 231 source-archive files ([inventory.json](inventory.json)).
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
- Source distribution on Windows Python 3.12.10: installed and ran the demo
  (checking it prints the diagnosis codes and no 1.x label), `summarize`, both
  examples, migration of a 1.2.0 trace, the OpenTelemetry commands and a
  composite verify ([sdist312.json](sdist312.json)).
- Browser review at desktop and mobile widths: the composite report rendered
  by the installed wheel, the homepage and the docs page, with no overflow,
  scripts, external references or leaked values
  ([browser-qa.json](browser-qa.json),
  [report](report-composite-desktop.png), [homepage](homepage-stack-mobile.png)).

## Pending and limits

- Public docs/support gate: pending. The 2.1.2 site and docs pages state 2.1.2
  as published and deploy only after publication. Private vulnerability
  reporting is enabled.
- The full source suite ran on Python 3.12 only; Python 3.11 and 3.13 to 3.15
  ran the installed-wheel checker.
- The first Linux guest boot stopped with a kernel panic (its IO-APIC timer
  check) while the host was busy running the source suite
  ([serial log](linux-failed-boot.log)). The next guest run started before the
  guest's venv had pip and failed at install. Both were set aside; the
  recorded Linux result is a clean boot and run of the same wheel.
- macOS has never been tested. Linux coverage is one emulated Alpine guest.
- One live run per framework, with one model each, shows the wiring works; it
  does not cover every model or SDK release. No MCP server, OpenTelemetry
  collector or tracing backend was used.

Gate states are in [checks.json](checks.json). GitHub Actions was not used.
