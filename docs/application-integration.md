# Integrating an application

ConseqaX explains captured application actions without using the refund
simulator, calling a model, or executing a write. Register each action's target
before running it, keep its responses and the agent's reported assessments, then
obtain a separate readback observation. A response is evidence about the request;
the readback is evidence about the external outcome.

Traces use schema `1.0`. The easiest way to build one is `TraceRecorder` (see
[capturing agents built with a framework](framework-integration.md)); the records
it produces (`Action`, `OutcomeContract`, `Event`, `ToolResponse`,
`AgentAssessment`, `Observation`, `VerificationResult`) can also be constructed
by hand with keyword arguments. `Trace.from_json(trace.to_json())` validates the
record types and identity links. It does not authenticate a source or prove a
predicate's domain semantics.

## Outcome verification

For an outcome that leaves records behind (rows, orders, tickets, files), start
with the built-in `RecordVerifier`. Use the predicate `record_present`;
`contract.expected` lists the field values a matching record must carry, and
`scope_fields` names the fields the readback snapshot covers:

```python
verifier = RecordVerifier(scope_fields=("order_id",))
receipt = capture.verify(observation, verifier=verifier)   # or verify(action, observation, verifier=...)
```

It checks the exact or minimum count, the commit deadline and the persistence
window, and returns `unknown` for unavailable, out-of-scope, incomplete, stale
or malformed readback. Record identifier, commit time, removal time, action,
actor and attempt field names are configurable; with the defaults the evidence
graph also links each record to its dispatch. `RefundVerifier` (the default of
`verify`) does the same for `refund_processed` payments.

For any other domain, supply a read-only verifier implementing the `Verifier`
protocol:

```python
class ApplicationVerifier:
    def verify(self, action: Action, observation: Observation) -> VerificationResult:
        ...
```

`verify` checks that the result is a `VerificationResult` whose action and
contract identities match, and that every evidence item identifies the supplied
observation with exactly its source and watermark. A receipt cannot precede the
observation's capture time. A result that crosses that boundary raises
`ReceiptError` before it can be used. `averify` does the same for a verifier whose
`verify` method is a coroutine.

The application owns the verifier's predicate, source authentication, scope,
record validation, completeness, deadline and persistence checks, and effect
origin rules. The wrapper cannot establish those facts or sandbox a verifier's
behavior. A tool acknowledgement, agent statement, or copied expected value is
insufficient independent evidence. Missing, unavailable, malformed, incomplete,
or temporally insufficient readback should produce `UNKNOWN` whenever the
predicate cannot be established. Positive witnesses and absence claims may have
different completeness requirements; define them for the domain.

Populate `attributable_effect_ids` only when trustworthy source metadata links
an observed effect to this action. A satisfied state may instead result from
another actor, or have unknown origin. Those distinctions must survive the
receipt. An origin link is evidence about provenance, not an intervention-based
causal attribution score.

## Target matching and findings

A verifier also records what `explain` needs to judge the agent's report:

- `target_effect_ids`: for a known outcome, the attributable effects that match
  the full target: requested payload, commit deadline and persistence horizon.
  Leave it `None` when the agent's success or failure does not refer to this
  contract, or when the verifier does not match targets; alignment then stays
  `unassessable`. An unrelated effect with the same action ID does not qualify,
  and an `unknown` receipt cannot have target matches.
- `findings`: domain facts such as `EXCESS_EFFECTS` or `PARAMETER_MISMATCH`, each
  a `Finding(code, effect_ids, detail)` with an UPPER_SNAKE_CASE code and the
  observed effects it rests on.

Setting `target_effect_ids` declares that the agent's `SUCCESS` or `FAILURE`
assessment concerns satisfaction of this contract. Known violations can then be
compared with those reports; known satisfaction requires at least one target
match before alignment or a lost-response diagnosis is claimed. Unknown outcomes,
unknown assessments, other-actor satisfaction and unconfirmed origin remain
unassessable.

`explain` never re-reads evidence details: domain interpretation happens once,
when the verifier runs, and the receipt is the verifier's claim.

## Outcomes with several parts

Some actions have more than one required effect: a refund is issued *and* the
ticket is closed, or a customer is compensated by a card refund *or* store
credit. Since 2.1, `all_of` and `any_of` build one outcome contract from part
contracts, each with its own predicate, expected values, deadline, stability
window and count, and `CompositeVerifier` checks each part with its own
verifier against the readback from that part's source:

```python
from consequa_x import (
    CompositeVerifier, OutcomeContract, RecordVerifier, RefundVerifier, all_of,
)

refund = OutcomeContract(contract_id="refund", predicate="refund_processed",
                         expected={"payment_id": "p-1", "amount_minor": 5000, "currency": "INR"},
                         deadline_ms=deadline, stability_ms=5_000)
ticket = OutcomeContract(contract_id="ticket", predicate="record_present",
                         expected={"ticket_id": "t-9", "state": "closed"},
                         deadline_ms=deadline, stability_ms=5_000)
capture = rec.register("resolve-1", "resolve_case", args, contract=all_of("resolve", refund, ticket))
...
verifier = CompositeVerifier(
    {"refund": RefundVerifier(), "ticket": RecordVerifier(scope_fields=("ticket_id",))},
    sources={"refund": "payments-db", "ticket": "crm"})
receipt = capture.verify((payments_readback, crm_readback), verifier=verifier)
```

The parts combine with three-valued logic, so unknown evidence stays unknown:
`all_of` is violated when any part is violated, satisfied when every part is
satisfied, and unknown otherwise; `any_of` is satisfied when any part is
satisfied, violated when every part is violated, and unknown otherwise. A part
whose source supplied no readback is unknown. The combined deadline and horizon
are the latest of the parts'.

The combined receipt keeps each part's evidence, tagged with the part's
contract ID, status, origin and reason, and the union of the parts' effects
and findings. It adds `PART_VIOLATED`, `PART_UNKNOWN` (when the outcome is not
satisfied) and `PART_OTHER_ACTOR` findings. Target matching is conservative: an
`all_of` outcome counts as produced by this action only when every part's
matching effects are this action's, and an `any_of` outcome when a satisfied
alternative's are. Parts can nest, with a nested `CompositeVerifier`.

Effect identifiers name one effect across the whole trace, as they do in the
evidence graph, so parts that read different sources should use distinct
identifiers. `poll_readback` takes a `read` function that returns one
observation per source, and `consequa-x verify` takes `--readback` once per
source with `--part-source PART=SOURCE` and `--scope-field PART=FIELD`.

## Offline artifact example

[examples/artifact_delivery.py](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/examples/artifact_delivery.py)
implements a second domain, `artifact_delivered`, using only the public API and
the Python standard library. It registers a path, content digest, deadline and
persistence horizon; captures a timeout response and failure assessment;
consumes a separately captured artifact-store snapshot; verifies it, recording
target matches; and round-trips the trace before explaining it. The fixture's
digest is computed from the bytes read back, rather than copied from the
requested digest.

Run it from the repository with an installed package:

```console
python examples/artifact_delivery.py
```

The default captured fixture contains the requested artifact with independently
reported action and actor metadata. The verifier records it as a target match,
so the timeout and reported failure diverge from the verified outcome. The
example also supports absent content, wrong content, unavailable readback,
another actor, and missing provenance, covered by application integration tests.
It performs no delivery, filesystem write, network request, or model call.

For production, replace the fixture with a separately authenticated read
adapter. Its `present_through_ms` field must come from a trustworthy persistence
witness or exhaustive history; observing current existence alone does not prove
past stability. A witness ending before the horizon leaves the result `UNKNOWN`;
it does not prove that the artifact was removed.

This example predicate requires exactly one matching delivery revision committed
in the closed interval from action registration through the horizon. That one
revision must commit by the inclusive deadline and have a presence witness
through the inclusive horizon. A second matching revision committed before the
deadline, at the deadline, or during the stability interval violates the
contract. A commit strictly after the horizon is outside its scope. Only
deadline-eligible revisions with sufficient persistence witnesses are target
matches; later origin-linked revisions are not. Implement and test other
predicates, current-state replacement semantics, or count semantics explicitly
in the application's verifier.
