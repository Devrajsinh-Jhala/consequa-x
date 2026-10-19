# ConseqaX 2.1.1: read-only paper impact review

Reviewed local Git objects at `3ff37d5` against the **measured 2.0 conformance
source `f64bf49`** on 19 October 2026. No network request, package import,
model/service call, test or measured-corpus rerun was made. Frozen worktrees
and existing source/data were untouched. `review.json` binds exact commit IDs,
Git blobs, source hashes, AST comparisons and retained release records.

## Exact change boundary

| Runtime paths | Measured 2.0 | Current 2.1.1 |
| --- | ---: | ---: |
| Total payloads | 48 | 54 |
| Existing paths byte-identical | | 36 |
| Existing paths modified | | 12 |
| Added paths | | 6 |
| Deleted paths | | 0 |

The retained distributed wheels show the same 36/12/6/0 path comparison.
The six added files are `composite.py`, `otel.py`, the integrations initializer,
and adapters for OpenAI Agents SDK, LangChain and Claude Agent SDK.

Exact unchanged files include `models.py`, `explanation.py`,
`record_verifier.py`, `graph.py`, `benchmark/targets.py`, the replay/decision
estimators, intervals, attribution, policies, payment simulator and Ollama
adapter. The complete path/hash map is in `review.json`.

Important distinctions among modified paths:

- **Default refund arithmetic:** the entire `RefundVerifier` class AST and
  `_peak_count` are unchanged. Its containing `verification.py` is changed.
- **Public verification routing:** `verify`/`averify` now accept a single
  observation or a nonempty sequence, select a multi-readback verifier when
  available, reject duplicate observation identities, and check receipt
  evidence against the supplied set and its maximum observation time.
- **Migration:** every migration function/class AST is unchanged; the module
  docstring uses the new project spelling. It calls the changed public
  verification wrapper, so this alone does not prove pipeline equivalence.
- **Wire schema:** version remains **1.0**. The bundled JSON schema is exactly
  equal after removing only its display `title`; validation definitions and
  identifiers are unchanged. The generator has the matching title change.
- **Capture/polling/report/CLI:** capture and polling support several readbacks;
  reports and commands add composite/OTel support. Branding-only changes occur
  in errors, research namespace documentation and the benchmark initializer.

Static tracing of the valid, default single-observation refund path reaches
the same refund method and corresponding one-observation identity checks.
This supports a **narrow source-continuity statement**. It is not another
503-trace execution or proof that all current imports, wrappers, new branches,
SDKs or platforms are covered by the measured 2.0 study.

Keep the 503-trace conformance labeled **2.0.0, source `f64bf49`**. Keep the older
matched model/judge/native-tool/CAR studies at their original frozen 1.1.0
pins. To claim measured 2.1.1 corpus conformance, make a separate prospective
source-bound offline check; do not silently update a successful old protocol.
The existing numerical estimators and target-helper source are unchanged,
which does not establish new empirical accuracy or current-package superiority.

## Retained publication evidence

The release is described as a maintenance update from 2.1.0; the composite,
telemetry and SDK additions landed in 2.1.0. Its build source is
`b73ecd00fc9b4b8b3f9b8182aa8ed652419d7e54`. Local publication/registry receipts
report upload to PyPI on 19 October at 15:15 UTC (20:45 IST), followed by an
isolated registry installation.

| Retained artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Wheel | 215,139 | `c86c02aacac53d51bd4335238c4f44b96098db9af354662b23722fab60ed3b98` |
| Source distribution | 676,766 | `9841f34842c89bbbdffa6776bbc5baf32e2288f25a35cfc1ad1e3f665021fa69` |

This review independently checked these retained bytes against the publication
record and verified all 54 wheel runtime payloads against the recorded build
source. It did **not** query current PyPI, the live site or GitHub APIs.
Publication statements therefore rely on the timestamped retained receipts;
no fresh online publication or Actions-status verification is implied.
Release receipts say GitHub Actions was not used.

The display name is now **ConseqaX**. Distribution/CLI `consequa-x` and import
`consequa_x` are unchanged. Preserve historical study filenames and citations.

## New engineering evidence and its limits

**Composite outcomes.** `all_of` and `any_of` combine part contracts and their
three-valued verdicts, source-specific observations, target metadata,
provenance and findings. Tests cover nesting, unknown/missing sources,
serialization, async, polling, reports and CLI. The two-part example uses two
local SQLite databases, a scripted policy and simulated time. It is not a
payment/CRM service experiment, benchmark score or independent validation of
all multi-part semantics.

**Telemetry.** OTLP JSON export, payload-enabled round trips, tool-span capture
and optional API emission are implemented. Installed tests use OpenTelemetry
API/SDK **1.45.1** with an **in-memory exporter**. No live collector or external
tracing backend was exercised. Do not turn structural export checks into a
claim of end-to-end interoperability with deployed backends.

**Offline SDK checks.** A separate installed-wheel extras check reports
**37 passed, zero skipped and zero provider calls** on Windows Python 3.12.10,
outside the checkout. Actual packages were used: openai-agents **0.24.0**,
langchain-core **1.6.12**, claude-agent-sdk **0.2.168**. OpenAI uses the SDK's
scripted model in a real runner; LangChain exercises real tools/callbacks;
Claude uses the SDK hook protocol through a scripted transport.

**Real-model smoke checks.** A different receipt, `live-integrations.json`,
retains three actual-model agent loops, one per SDK. OpenAI Agents and
LangChain use local Ollama `qwen3:4b-instruct-2507-q4_K_M`; Claude Agent SDK uses
**Haiku through the existing Claude Code login**, which involves remote
inference. The combined live check is therefore not offline or zero-provider-call.
Each observed loop calls one local SQLite refund tool, commits a row and then
receives the injected timeout. Capture matches the calls that ran; each agent
reports failure, and readback supports satisfied state/confirmed origin and
contradicted alignment. The smoke `passed` criterion tests capture matching
and absence of uncaught run error, not comparative model accuracy.

The Git release directory retains aggregate outputs, not pinned model
digests/seeds, provider-call counts/full provider transcripts, or per-framework
trace/database files. One case, model and run per framework supplies wiring
evidence. It does not establish generalization, SDK-wide correctness, cost,
policy recovery, retry-prevention benefits or a controller comparison. Keep
these three checks separate from every frozen research denominator.

**MCP wording correction.** The release says no MCP server was used. The live
Claude code actually creates an **in-process SDK MCP billing tool server** with
`create_sdk_mcp_server`. For the paper, say **no external/deployed MCP-service
interoperability validation**, not no MCP server of any kind. There was also no
live OTel collector/backend check. No release document was edited by this review.

## Platform scope

Retained installed core-wheel checks cover one Windows host with Python
**3.11.9, 3.12.10, 3.13.16, 3.14.8 and 3.15.0**, plus one emulated QEMU Alpine
Linux **3.24.2/Python 3.14.8** guest. SDK extras/live runs were Windows 3.12 only;
the Linux check covers core behavior and missing-extra import errors. macOS
remains untested.

The final-release Python 3.12 source suite reports **1,952 passed, 27 skipped,
241 subtests**. Newer-interpreter full suites ran at earlier `4f2cf80`, before
the version bump: each has one initial demo-data comparison failure, attributed
in the release notes to concurrent regeneration, followed by a passing rerun.
Do not describe those logs as uniformly failure-free full suites at the final
release revision. This review did not rerun tests or independently establish
the reported race's cause.

## Suggested paper wording

> The current ConseqaX 2.1.1 release adds composite outcomes, telemetry and SDK
> integration facilities within schema 1.0. The saved-trace conformance study
> remains pinned to 2.0.0 source `f64bf49`. A static source comparison finds
> unchanged models, explanation, target helpers, numerical estimators and
> built-in refund-verifier method, alongside changed multi-readback dispatch
> and receipt-checking wrappers. We do not relabel the 2.0 measurements as
> validation of the complete 2.1.1 release. Separately retained SDK tests and
> three real-model smoke loops are software-integration evidence, outside the
> paper's frozen research denominators.

Use the version-specific [2.1.1 package destination](https://pypi.org/project/consequa-x/2.1.1/)
and retained release record for current availability, with the publication
boundary stated above. Keep source authentication, readback completeness,
independent human validation, immutable archive and venue requirements as
separate responsibilities; no new scientific result follows from publication.

Root follow-up: a fresh read-only official PyPI JSON request also matched both retained artifact sizes and SHA-256 values; see [registry-verification.json](registry-verification.json). No model or install was run.
