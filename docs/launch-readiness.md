# Version 1.1 launch readiness

The four P0 improvements below are implemented for version 1.1: an offline HTML
report, minimal disclosure by default, public documentation/support and an
installed-package compatibility checker. The [1.1 release checklist](v1.1-release.md)
and its retained artifact receipts determine whether all release gates passed.
The version-1 core and schema 0.1 remain unchanged. P1 items remain future work.

The original product review was conducted on 16 October 2026 against 1.0.0;
the following inventory describes that checkpoint and motivates the 1.1 scope.

The strongest launch audience is Python developers debugging consequential
agent tools: a timeout, retry, or confident agent report can disagree with the
independently observed result. Lead with that concrete problem and a runnable
example. More estimator variants and a second language package would add less
immediate adoption value than making one captured run easy to inspect.

## What is already shipped

[`consequa-x==1.0.0` is public on PyPI](https://pypi.org/project/consequa-x/1.0.0/).
The following are supported by code and release evidence, rather than promises
for the next version:

| Capability | Current evidence |
| --- | --- |
| Portable typed traces and strict schema-0.1 decoding | `src/consequa_x/models.py`, `src/consequa_x/schema.py`, packaged JSON Schema and `py.typed` |
| Separate response, agent assessment, verified state and origin | `src/consequa_x/verification.py`, `src/consequa_x/explanation.py` |
| Application-specific verifiers and target matchers | Public `Verifier`, `TargetMatcher`, `verify` and `explain` interfaces; `examples/artifact_delivery.py` uses no benchmark imports |
| Graphs preserving successive observation witnesses | `src/consequa_x/graph.py`, `docs/graph-witnesses.md` and graph identity tests |
| Offline demos, explanations and research exports | CLI commands, twelve trace fixtures, source-archive examples/docs/tests/scripts; ordinary core usage requires no model or runtime dependency |
| Bounded, explicitly scoped research replay | Research interfaces, saved refusals and costs, independently audited synthetic studies; optional local Ollama adapter |
| Verified public distribution | `output/release-1.0.0-2026-10-15/checks.json`, `publication.json` and `registry-install.json`; wheel and source archive independently downloaded and hash checked |
| Tested installation scope | Windows Python 3.11/3.12; full frozen-source suite passed 1,480 tests plus 240 subtests; installed-artifact and public-index checks are recorded separately |

At the 1.0 checkpoint, the graph exported structured data without a visual application report.
Application users construct records directly; benchmark recording helpers are
not a general application recorder. No general redaction API, LangChain adapter,
OpenTelemetry exporter, hosted dashboard or npm distribution was found in the
reviewed source. The paper's figures do not add these package features.

## P0: a bounded release to prepare for the hard launch

Recommend a `1.1` release centered on **one offline report command**, supported by
public onboarding and a small compatibility gate. Preserve the version-1 core
and wire schema. Do not expand the research contribution or rewrite historical
study artifacts as part of this work.

| Work | Acceptance criteria |
| --- | --- |
| Offline trace report | A proposed `consequa-x report trace.json --output report.html` produces one self-contained file from a validated trace. It needs no web server, model, API key, remote assets or network requests. It displays a chronology, contract, response, reported assessment, verification, origin and evidence graph. Repeated effect witnesses remain individually visible. `unknown`, `other_actor` and `unassessable` stay explicit; graph edge labels distinguish order, dependency, provider provenance and supplied estimates. |
| Safe report presentation | Arbitrary captured strings are escaped before entering HTML. Embedded payloads cannot become executable markup or script. Keyboard navigation, text labels alongside colors, print layout and long-value wrapping work. Invalid trace/schema input and existing output files are refused before writing. Reports never modify the source trace, run a verifier, execute an application action or perform replay. |
| Minimal disclosure by default | The default report omits free-text rationales, arbitrary payloads, raw IDs, paths, source names and other user-controlled values that are not needed for its structural view. Use consistent local display aliases for linked identities. Any option revealing captured fields is explicit and documented as potentially sensitive. Hidden content must be absent from the file, including embedded JSON, titles, attributes and comments. Keep the untouched original trace separately; a reduced report is a presentation artifact, not replacement verification evidence. This is deliberate field omission, not a universal PII-detection guarantee. |
| Public quickstart and feedback route | A user without repository access can read the install/API guide, run a five-minute synthetic example, see the resulting report, understand source-trust assumptions and submit a reproducible problem. Add real public Documentation, Changelog, Issues/support and Security-policy URLs once available. Keep the existing repository private. A separate public documentation/support location can satisfy this gate without exposing retained research data. |
| Release and compatibility evidence | From a built wheel outside the checkout, run trace round-trips, report generation, output preservation and the artifact-delivery example on Windows plus one real Linux environment. Add a real macOS run before claiming macOS is tested. Record exact OS/interpreter versions and failures; never infer a platform result from `py3-none-any`. Run locally or on independently available hosts: GitHub Actions remains disabled. |

Public onboarding should put the artifact-delivery example before the long
research command list, then show the refund timeout example. Both should use
captured synthetic data, explain where a real application's independent readback
comes from, and demonstrate `unknown` when evidence is insufficient. Add a
copyable bug-report template requesting package/Python/OS versions, the command,
the error and a synthetic minimal trace. A report containing real customer data
must not be the default requested attachment.

The public source archive already provides documentation as a fallback, but a
private GitHub issue link is not a usable public feedback channel. Current
`pyproject.toml` lists only private Repository/Issues URLs. The contributor guide
has been corrected in the working source to describe the shipped stable release;
the published source archive retains its dated build-time documentation. Published
`1.0.0` files are immutable; include the corrected guide and metadata in the next
reviewed release. PyPA documents
the recognized Documentation, Changelog, Issues and Security URL labels in its
[project-URL specification](https://packaging.python.org/en/latest/specifications/well-known-project-urls/).

For the HTML implementation, Python's standard library already supplies
[`html.escape`](https://docs.python.org/3/library/html.html#html.escape). Escaping
must match the output context; data should not be interpolated into executable
JavaScript. This supports retaining a dependency-free core. Test actual rendered
reports using long strings, HTML-like payloads, quotes and repeated witnesses,
not just a snapshot of one successful fixture.

## P1: the next adoption improvement after the report

Build a small capture/export helper before collecting many framework adapters.
It should reduce the amount of record-construction code while preserving the
application's explicit verifier and independent observation boundary.

| Candidate | Concrete acceptance criteria |
| --- | --- |
| Application recorder and bundle export | A documented session API accepts a predeclared action/contract, appends typed events/responses/assessments/observations and finalizes a validated `Trace`. It exports the original trace, optional explanation, schema and a file/hash inventory to a new directory. Identity, parent-link and timestamp checks match the existing constructors. Failure/cancellation and two concurrent independent sessions cannot merge histories. It does not infer a completed effect from a tool response, invent observations, automatically retry a write or promise source authentication. |
| One optional framework integration | Choose LangChain only if early users need it. A separate extra/adapter can capture tool dispatch, returned response or exception, attempt IDs and declared assessment semantics. Keep verifier/readback supplied by the application. Sync and async test doubles must prove the tool handler runs exactly once per captured attempt and exceptions/cancellations are preserved. No model credentials or paid calls belong in default tests. Record the tested integration version range; plain `import consequa_x` must still work without LangChain installed. |

LangChain currently documents middleware hooks around tool calls and distinguishes
them from hooks around model/agent steps. Its wrapper can invoke a handler zero,
one or several times, so a passive capture adapter must deliberately preserve
invocation count and must not add hidden retries. This is a proposed integration,
not existing Consequa-X functionality. See LangChain's official
[custom middleware documentation](https://docs.langchain.com/oss/python/langchain/middleware/custom).

A one-page adapter conformance checklist should accompany either change:
registered target, separately captured readback, source completeness/watermark,
deadline/persistence semantics, origin qualification, unknown handling and
identity linkage. Reuse the artifact domain for this checklist; additional
synthetic domains are useful only when they test a different adapter requirement.

## A practical launch gate

Launch the product around **inspect a captured agent action and see what the
evidence supports**. The minimum convincing demonstration is: install from PyPI,
generate a synthetic timeout-after-commit capture, open its offline report and
follow the independent observation to the result. Include a second run where
missing evidence leaves the result unknown. An unaffiliated Python developer
should complete this path from public instructions without repository access or
help from the maintainer.

Before announcing the next release, retain one checklist with:

1. Successful public wheel/source installation and an artifact hash receipt.
2. One report example and one custom-verifier example run from that installation.
3. Browser review of normal, unknown, conflicting-witness and hostile-text reports.
4. A stated platform/interpreter support table based on actual runs.
5. Working public documentation, changelog, support and private vulnerability-reporting instructions, checked without repository authentication.
6. A maintainer support policy: where bugs go, how supported versions are stated,
   and how a breaking change/deprecation will be communicated. Promise response
   times only if the maintainer can sustain them.

This is a finite release scope. Hosted multi-user storage, automatic remediation,
universal redaction, numerous provider adapters, a TypeScript SDK and further
attribution algorithms can wait for actual adoption evidence. A later npm SDK
would need its own maintained API, shared schema/conformance fixtures, integer
and identity compatibility, registry release checks and support commitment.

The existing paper and audited synthetic studies support the framework's
declared behavior. Hard-launch messaging should not claim provider-independent
truth, automatic causal proof, improved live-agent accuracy, universal production
verification, a new estimator or superiority over a matched baseline. Product
usability can improve independently of those still-open research questions.
