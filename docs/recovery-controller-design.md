# Research recovery controllers: frozen public policy

This library lives in `research/recovery_study/controllers.py`, outside the
distributed package. It imports neither an application world nor a corpus nor
evaluation truth. Its development tests use only synthetic JSON fixtures. The
controller author did not inspect heldout scenarios, the world-design document,
old empirical outputs, or study results. There are no model or service calls.

## Public interface and information boundary

Construct `Controller(method, *, action_id, actor, expected, scope, deadline_ms,
stability_ms, source, read_times, max_dispatches=2, exact_count=1,
scope_fields=None, native_idempotency=False)`. `scope_fields` defaults to the declared scope's keys and
must name exactly those keys. Expected business fields cannot use reserved
provenance/time metadata names. The five method identifiers are:

| Method | Reported global state | Provenance report | Recovery/query policy |
| --- | --- | --- | --- |
| `response_retry` | Success ACK means true; error means false; unresolved timeout means unknown | Same ACK/error proxy applied to this-action completion | Retry timeouts up to the shared cap, before the original deadline |
| `readback_state` | Complete trusted evidence through the fixed horizon | Unknown for state success; false for known state failure | Shared bounded read opportunities and terminal gate |
| `reference` | Independent standard-library interval/count rule | Independent provenance interpretation | Shared bounded read opportunities and terminal gate |
| `consequax_one_read` | Public 2.1.1 `RecordVerifier` | Receipt target IDs plus missing-provenance uncertainty rule | Optional predeadline terminal-gate reads, then one final horizon-eligible read |
| `consequax_poll` | Public 2.1.1 `RecordVerifier` | Same rule as the single final read arm | Shared bounded read opportunities until known or exhausted |

The classical bounded idempotent retry comparator **is** `response_retry` when
the provider honors operation keys. There is no duplicate alias arm. Every
dispatch in every arm carries the unchanged logical operation ID as its
idempotency key. No arm disables provider idempotency.

`begin(at_ms=0)` registers the fixed declaration and returns the initial
dispatch. `on_response(response, response_at_ms)` admits only public response
fields: status, attempt_id, response_at_ms, result, provider_request_id, and
optional terminal_not_committed. `on_readback(observation)` admits exactly the
public `Observation.to_dict()` fields. `decide(now_ms)` returns kind, at_ms,
reason, and dispatch identity/read scheduling fields where relevant. Its kinds
are dispatch, read, wait, stop and abstain. A driver delivers the corresponding
callback before requesting another decision. Callback times must be monotonic;
observation IDs must be unique. Inputs and returned reports are copied.

There is no constructor argument for case identity, scenario family, hidden
configuration, evaluator truth, or result labels. The registered source is an
application trust declaration; source identity alone does not authenticate a
database. The runner must admit the source/scope/clock/history and per-attempt
terminal guarantee through the public source receipt before constructing any
arm. All methods receive the same admitted JSON schema and query opportunities.
Responses and records retain public application fields only.

## Fixed evidence law and separate claims

Let registration be t0, deadline D, stability window W and fixed horizon H=D+W. A
complete admitted observation must be available, cover the registered scope,
come from its declared source and have watermark at least H. Every record
must have a unique nonempty effect ID, valid commit/removal times, valid
optional provenance strings, and agree with its declared scope. Otherwise its
final outcome is unknown.

A target candidate matches every expected business value, commits in [t0,D]
and is not removed at or before H. With exact_count=k, exactly k candidates
must exist and the maximum simultaneous matching count over the closed
interval [D,H] must equal k. With exact_count=None, at least one candidate is
required. Simultaneous commits and removals are evaluated together. Historical
removals and transient extra records must remain in readback history.

The reference implements this law independently, by evaluating counts at
interval endpoints/change times. The package uses its public verifier. The
reference imports no package verifier or package internals; a test prevents
package imports during its operation. Synthetic development grids check
agreement on timing, removal, count and provenance combinations. Agreement
with an equally informed implementation is the expected result, not a defect
to tune away.

Reports deliberately separate these quantities:

- `reported_state` and its explicit alias `reported_success` concern the
  **global fixed target state**. `reported_success_target` labels this meaning.
  `final_target_state` is the state established by admitted evidence; it remains
  unknown for the response proxy even when that proxy claims success.
- `reported_action_linked` requires the full global target contract and a
  qualifying target candidate authenticated to this action. A known global
  violation makes this claim false even if an own matching witness exists.
  `this_action_linked_target` is its evidence field. The response proxy makes its own action-linked ACK/error claim;
  readback_state abstains on provenance when state holds; it can still infer
  linked-contract failure from a known global failure without reading identity.
- A matching action ID with absent or matching actor confirms linkage. Explicit
  different action/actor metadata excludes this action. Missing linkage or
  conflicting action/actor metadata remains unknown. A complete snapshot with
  no target candidate establishes false for candidate existence. Provenance
  does not change a globally satisfied state into a failure. The package
  adapter assembles its linked claim from public receipt status/target IDs and
  its own explicit uncertainty handling; it does not call the reference's
  provenance implementation.
- `definite_report`/`abstained` refer to the global claim.
  `action_linked_definite_report`/`action_linked_abstained` refer separately to
  the attribution claim. Dispatches, reads, final_reads and waits are charged
  explicitly, with their common budget ceilings and the full decision log.

The evaluator separately owns target truth, unwanted/duplicate effects,
completion by any later recovery horizon, and safety outcomes. Controllers
never see those values. A later recovery cannot retroactively satisfy D.

## Safe retry windows and the watermark limitation

A source watermark through t certifies historical coverage only. Even a fresh,
complete empty snapshot at t<D cannot establish that a timed-out operation
will not commit between t and D. Existing matching evidence can be observed
provisionally; a final satisfied claim still requires H coverage. Waiting for
H to prove fixed-target absence leaves no ordinary predeadline retry window.
The framework's `retry_advice` itself explicitly warns about later commits.
Its `retry_permitted` receipt at H is consequently not authority to rescue
the already closed original deadline.

The application policy permits a productive predeadline retry only if:

1. Every dispatched attempt has returned the admitted per-attempt
   `terminal_not_committed: true` guarantee. It certifies that exact attempt
   ended without an effect and cannot commit later. A newer reply never
   resolves an earlier ambiguous request. Missing/false guarantees block the
   gate, including provider replays that cannot resolve earlier work.
2. A complete, trusted, scope-correct readback is fresh through the decision
   time and establishes no relevant effects through that time.
3. The decision occurs strictly before the unchanged D and below the common
   dispatch cap. The retry carries the unchanged operation key.

There is one separately declared provider capability: when the admitted
`native_idempotency` is true, every readback arm may retry an ambiguous timeout
before D up to the same dispatch cap with the same operation key, without the
terminal/absence gate. Atomic provider deduplication reserves pending work as
well as completed work, so this request cannot create a second own operation.
The response remains an acknowledgement rather than final outcome evidence.
An absent/false provider capability never enables this exception. Every arm
receives the identical public capability, recorded in its report.

This is an explicit application-side rule applied equally to readback_state,
reference and both package arms. The package arms construct a separately
labelled provisional public `RecordVerifier` receipt ending at the current
time, without replacing the registered fixed contract. These receipts appear
under `provisional_verifications`; the trace's fixed-contract receipt remains
unknown before H. Ordinary `retry_advice` is retained as evidence-derived
advice, with its application safety gate visible in the decision reason.
Without all three conditions or the explicit native-deduplication exception,
unknown never opens a retry. The gate resolves
future commits from this controller's attempts, not arbitrary future writes
by other actors; global race freedom is not claimed.

## Polling, resource matching and the single final read ablation

`read_times` and `max_dispatches` are shared opportunity/budget ceilings.
Reads use exactly the admitted application observation at the actual query
time; worlds do not tailor readback to a controller. Different writes can
produce different later states and thus different legitimate observations.
Actual read counts can differ because an arm stops when its declared report
is known, or voluntarily uses fewer opportunities. No hidden information or
extra queries compensate a stronger arm.

The single final read arm skips predeadline opportunities unless all attempt
terminal guarantees make a gate query relevant. It may then query and retry
before D under the common gate. Its first query performed at or after H is
its only final read. Thus it is not forced to make its sole final query before
the evidence could possibly settle. The polling arm can use subsequent
scheduled reads after H to resolve lag, incompleteness or unavailability.
At exhaustion, unresolved global state is an explicit abstention. No physical
sleep, wall-clock loop, hidden query, postdeadline dispatch or model call occurs.

The package arms use the public `TraceRecorder`, `OutcomeContract`,
`RecordVerifier`, `Observation` and `retry_advice` APIs from version 2.1.1.
They implement callback-based bounded polling because the public synchronous
`poll_readback` helper owns a blocking read/sleep loop and cannot consume this
runner's matched externally scheduled observations. This is application
integration work, not a new package verifier or an autonomous policy claim.

## Development validation and freeze

Run only `tests/test_recovery_controllers.py` before the development freeze.
The tests cover acknowledgement proxies, operation-key reuse, unknown/lagged
evidence, fresh terminal gates and their failure conditions, the fixed
deadline, state versus action linkage, single-final-read versus continued
polling, malformed records, interval/count parity, and callback admission.
No heldout case, world implementation, old output, empirical study record,
package source edit, workflow edit, staging or commit is needed for these
checks. The root freeze manifest records SHA-256 values for this source,
test file and design document before any measured execution.

## Precollection integration checks, 20 October 2026

The prospective runner, not this reusable policy class, enforces the exact
installed 2.1.1 distribution and source bytes for measured execution.
Development fixtures can exercise the same public API on compatible later
2.x code without relabeling the frozen 2.1.1 experiment.

The primary endpoint is `operational_safe_recovery` over all scheduled slots:
completed safe recovery contributes one and a failed run contributes zero.
A failure leaves physical/semantic outcomes unavailable; it is not invented
as an observed unsafe outcome. The observed-only `safe_recovery` endpoint is
secondary. Read and dispatch budgets, native idempotency and terminal evidence
remain identical public capabilities for every arm.

Executing checkout/import origins must equal the frozen source root. One
canonical run claim per protocol hash under that root prevents copying the
protocol to start another run. Human-packet identifier substitutions reserve
aliases disjoint from every original string, preserving predicate equality.
These are precollection integrity checks, not measured empirical findings.
