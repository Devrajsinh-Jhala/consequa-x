# Matched native guard and package receipt condition

The implemented condition is `conseqax_guard`. Its control law is the unchanged
upstream LIMBO `OutcomeGuard` from commit
`2db09fba22a0572a70639162a808906409f612a8`, instantiated through the original
`limbo.policies.make_policy("guard", episode_id)`. The comparison measures
conformance and receipt integration. It does not introduce a new decision
algorithm or imply an advantage over this strong native baseline.

## Runnable seam and public information

The trusted launcher may replace only `limbo.agent.make_policy` for one episode
and restore it in `finally`. Invoke:

```python
from research.limbo_agent.boundary import BoundaryLimits
from research.limbo_agent.policy import make_policy

policy = make_policy(
    condition_name, episode_id, journal=framework_journal.append,
    limits=BoundaryLimits(execute=96, verify=64, wait=64,
                          total_wait_seconds=172800),
)
```

`vanilla`, `sdk_retry3`, `guard`, `rules` and `vbr` are delegated to the original
factory unchanged. Oracle names, assumed-wait extensions and unknown names are
refused. `conseqax_guard` returns the native-facing `NativeReceiptPolicy`, with
the normal `vanilla` prompt, no reflection, and the native intervention list.
One instance binds to one runtime. The shim gives the package-facing
`ReceiptGuard` only the existing `PublicRuntimeBoundary`.

The original native guard accesses a compatibility facade containing copied
contract flags and declared identity/key/SLA evaluators, real execute/public
verify, a scalar virtual clock, an audited wait and the last actual dispatch
start time. The facade's `world` has no entities, ledger, pending requests,
target predicates, fault plan, settling method or service callbacks. Its
timestamp-only event view has no fault or effect fields. Native contract
evaluators remain trusted pure functions of public proposed arguments.
No task-definition module is imported by this integration.

These restrictions are trusted-code information boundaries, not protection
against hostile Python introspection or arbitrary code modification. Upstream
native baseline policies continue to receive the original runtime; the
non-oracle guard code's allowed accesses are what the adapter preserves.
The evaluator alone constructs worlds, injects faults, settles and grades.

## What the SDK actually does

Each real `verify(..., truth=False)` result is converted to a genuine
ConseqaX **2.1.1** Action, OutcomeContract and Observation. `cx.verify` invokes
the explicitly supplied public-report verifier and returns a typed
VerificationResult. The guard consumes status/detail reconstructed from that
receipt after checking its content hash and bindings; it does not bypass the
receipt with a raw native status. SDK input contains only public tool arguments,
original dispatch time, current virtual observation time and the returned
public report. Origin is always **unknown**.

The native `found` status maps to a satisfied current-visible-match predicate;
`absent` maps to violated. Partial, unverifiable, unknown and future native
statuses map to unknown while retaining their exact original status/detail.
The original guard consumes those retained native statuses and therefore
preserves its partial-batch, lag wait, key insertion and suppression behavior.
The package cannot convert `absent` into proof that an in-flight request will
never commit. Its contract deadline is a schema registration horizon, not an
execution deadline or durable-settlement guarantee. Matching semantics remain
the native verifier's matching semantics; the custom SDK verifier does not
independently query or validate a second service.

The receipt journal is separate from the model-visible observations, which
remain byte-equivalent under the unchanged native serializer for matched
proposals. A failed receipt audit sink closes subsequent package dispatch and
verification. The caller must preserve the failure and stop the episode.
Every public verification has exactly one receipt; metadata lookups are
separately journaled. No extra service verification is introduced by receipts.
`audit_framework_wheel(path)` binds all **54** installed payload files, including
`py.typed`, to wheel SHA-256
`c86c02aacac53d51bd4335238c4f44b96098db9af354662b23722fab60ed3b98`.
It refuses different versions, import-path shadowing, missing/changed payloads
and unexpected noncache files. It neither installs packages nor binds every
third-party dependency payload.

## Native integration checks and cost scope

The focused test suite imports only native implementation modules: world,
services, runtime and policies. Invented worlds use synthetic project/table/
service identifiers and simulated mail recipients under `example.invalid`.
They do not load an actual task, target, fixture, case study or released result.
No model is called and no service outside the simulator is contacted.

The factorial parity check uses **11** invented operation configurations,
all **13** native fault modes, and both native/keys-everywhere contract
variants: **286** cases. Each case compares four identical proposed reissues,
then native settling. It compares returned observations, native interventions,
actual tool events, public verification inputs/results, virtual waits, entity
state, ledger and pending metadata. It includes supported and unsupported
social key/read-back paths, billing charges/refunds, ticket creation/comments,
simulated mail, single/batch data insertion and deployments. Separate checks
cover exact SDK status preservation, receipt binding rejection, actual
read/unknown/finish dispatch, unavailable simulated operator, work ceilings,
audit-sink failure, minimal facade shape and framework payload identity.

Native public verifier functions in this pin do not themselves append a
ToolEvent or advance virtual time. They directly apply the simulator's declared
read-back abstraction, with domain-dependent match/filter semantics. Tests
retain their invocation counts and verify their zero virtual-clock increment.
This is an upstream simulator convention, **not** a claim of zero real API
latency, one real read per verification or free verification. The collector
must report separate execute/verify/wait/flush boundaries, native effects and
wall time. The SDK's added wall/serialization work must be measured rather
than assigned zero because the virtual simulator clock does not advance.

This integration validation establishes expected control-law parity on
invented worlds. Actual benchmark outcomes require the prospectively frozen
first-attempt paired matrix, unchanged native grading and independent replay.
No numerical task-success or model-performance conclusion follows from these
tests alone. An unchanged native guard may retry an absent observation before
a late request commits, and one-time found suppression can later allow another
same-intent write. Preserving those limitations is part of the matched design.

On 22 October 2026, the selected native Python environment passed **305** new
policy checks plus **60** existing public-boundary checks (**365 passed**, 7.07
seconds). Ruff passed for the new source and tests, and the pinned upstream
checkout remained clean. This count includes the 286 factorial parity cases
and targeted receipt, failure, capability and wheel-identity checks; it is
not a count of benchmark tasks or independent model runs.
