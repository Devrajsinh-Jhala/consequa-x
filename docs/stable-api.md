# Stable core API: version 1

This is the core compatibility contract for version 1. Release-specific build,
validation and publication status belong in [release readiness](release-readiness.md)
and the release receipts.
Version 1 freezes the evidence core after application integration, graph integrity
fixes, output preservation and installation conformance checks. It supports
captured application actions and explicitly supplied domain adapters.
It does not supply a production payment provider or a universal replay engine.

## Supported public interface

The stable surface is exported from `consequa_x`: typed trace records and enums,
`Verifier`, `RefundVerifier`, `verify`, `TargetMatcher`, `explain`,
`ConsequenceExplanation`, `build_graph`, `ConsequenceGraph`, `Intervention`,
`EffectEstimate`, `leave_one_out` and `recency_attribution`. The existing
policy-boundary records/protocol and scripted refund policy remain available.
`consequa_x.schema.get_trace_schema` and `validate_trace` are supported.

Version 1.1 adds `render_report(trace, *, include_details=False) -> str` and the
`report` CLI command. The renderer produces offline HTML from a revalidated
snapshot, with structural aliases by default and an explicit escaped full-trace
details mode. It does not run verifiers, target matching or replay. See
[offline reports](offline-reports.md) for the disclosure and preservation contract.

Version 1.2 adds `TraceRecorder`, which records one action step by
step and returns the same validated `Trace` a caller could build by hand, plus
`capture_tool` and `TraceRecorder.call`/`attempt` to record a synchronous tool
call. The recorder runs only the tool function it is handed and never reads
sources or decides outcomes. `RecordVerifier` and
`RecordTargetMatcher` add a generic `record_present` predicate with the refund
verifier's evidence discipline.

The wire schema stays at `0.1`: the software version and trace schema version
are separate. Existing alpha trace JSON remains readable. Unsupported schema
versions, unknown record fields, invalid identities, inconsistent chronology and
dependency cycles fail validation. Enums remain string-valued; money is integer
minor units and times are integer milliseconds where the adapter declares them.
Unknown readback is never silently converted to a numeric failure.

`verify(action, observation, *, verifier=None)` preserves the refund default and
accepts an explicit trusted application adapter. `explain(trace, estimates=(), *,
target_matcher=None)` performs no replay. Domain-specific assessment matching is
explicit; other domains stay unassessable without it. See
[application integration](application-integration.md) for responsibilities and
the non-simulator example.

Existing core call signatures and valid schema-0.1 records remain supported
through version 1.x. Incompatible core changes require a new major version;
new incompatible wire formats require an explicit new schema version, without
silently reinterpreting old records. Deprecations will be documented in the
changelog and supported through the current major series. Internal underscore
helpers are not public interfaces.

## Graph and output contract

Graph nodes and edges retain typed meanings rather than implying causal
necessity. Repeated effect identifiers use separate observation witnesses and
identity links. Consumers must handle these kinds as documented in
[graph witnesses](graph-witnesses.md); the earlier alpha's repeated-witness node
shape is corrected in version 1. Reserved source fields are retained separately
from graph context. Attribution candidates must identify captured events.

CLI commands generating runs require a new or empty output directory. Existing
trace/explanation files are preserved; `explain --output` requires a new file and
cannot replace its input. Choose a separate output path for each run. These
commands assume the caller gives one process ownership of its output path.

The schema and model constructors enforce record structure. At the adapter boundary:

- `verify` raises `TypeError` for an argument that is not an `Action` or
  `Observation`, a verifier without a callable `verify` method, or a verifier
  result that is not a `VerificationResult`. A receipt whose contract, evidence
  identity, source, watermark or capture time violates the supplied boundary
  raises `ValueError`.
- `explain` raises `TypeError` for an argument that is not a `Trace` or a matcher
  without a callable `matching_effect_ids` method. Missing verification evidence,
  domain-invalid known refund details, and an invalid matcher result raise
  `ValueError`. Matcher results must be a tuple of unique nonempty attributable
  effect IDs; a different return type also raises `ValueError`. The method is
  checked for callability but never executed for an `UNKNOWN` receipt.

File errors produce `OSError`. The CLI reports these controlled errors with exit
status 2. Exceptions raised inside an application adapter propagate unchanged;
adapters must document their own failure behavior. This does not promise a
uniform exception type for arbitrary misuse of every public API.

## Research interfaces and compatibility

Modules under `consequa_x.benchmark`, exact policy prompts, experimental CLI study
commands and estimator/refusal settings are declared research interfaces. Their
protocols and artifacts pin source revisions; they are not an open-ended promise
that every research procedure is frozen as part of the core API. Method changes
must be named, recorded and preserve historical data.

Python 3.11+ is declared; release receipts identify the exact tested interpreters,
platforms and installation checks. A pure-Python wheel does not establish a test
result on every platform. Optional local Ollama inference requires a configured
server/model; core imports and offline examples require no model credentials or
required runtime dependencies. GitHub Actions remains disabled.
