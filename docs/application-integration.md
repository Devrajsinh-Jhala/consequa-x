# Integrating an application

Consequa-X can explain captured application actions without using the refund
simulator, calling a model, or executing a write. Register the target before the
action, retain the response and the agent's reported assessment, then obtain a
separate readback observation. The response is evidence about the request; the
readback is evidence about the external outcome.

The public records and trace JSON schema remain at version `0.1`. An application
uses `Action`, `OutcomeContract`, `Event`, `ToolResponse`, `AgentAssessment`, and
`Observation`, then adds a `VerificationResult`. These records, `Evidence`,
`ResponseStatus`, `Verifier`, and `TargetMatcher` are available from `consequa_x`.
`Trace.from_json(trace.to_json())` validates the record types and identity links.
It does not authenticate a source or prove a predicate's domain semantics.

## Outcome verification

`verify(action, observation)` retains the built-in `refund_processed` verifier.
For another domain, explicitly supply a read-only adapter:

```python
receipt = verify(action, observation, verifier=application_verifier)
```

The adapter implements the typed `Verifier` protocol:

```python
class ApplicationVerifier:
    def verify(self, action: Action, observation: Observation) -> VerificationResult:
        ...
```

The wrapper checks that the result is a `VerificationResult`, that its contract
identity matches the action, and that every evidence item identifies the
supplied observation with exactly its source and watermark. A receipt cannot
precede the observation's capture time. A result from another contract, source,
observation, or watermark raises a controlled error before it can be used.

The application owns the adapter's predicate, source authentication, scope,
record validation, completeness, deadline and persistence checks, and effect
origin rules. The wrapper cannot establish those facts or sandbox an adapter's
behavior. A tool acknowledgement, agent statement, or copied expected value is
insufficient independent evidence. Missing, unavailable, malformed, incomplete,
or temporally insufficient readback should produce `UNKNOWN` whenever the
predicate cannot be established. Positive witnesses and absence claims may
have different completeness requirements; define them for the domain.

Populate `attributable_effect_ids` only when trustworthy source metadata links
an observed effect to this action. A satisfied state may instead result from
another actor, or have unknown origin. Those distinctions must survive the
receipt. An origin link is evidence about provenance, not an intervention-based
causal attribution score.

## Assessment and target matching

`explain(trace)` uses refund payload and timing rules for refund contracts.
Other predicates receive a domain-neutral explanation. Their details are never
treated as money, refund counts, or currencies. Their assessment alignment
stays `unassessable` unless an application supplies target semantics:

```python
explanation = explain(trace, target_matcher=application_target_matcher)
```

The typed `TargetMatcher` protocol implements
`matching_effect_ids(action, verification) -> tuple[str, ...]`. It must check
the captured effect's requested payload, commit deadline, and persistence
horizon. Return only unique IDs within the receipt's `attributable_effect_ids`.
An unrelated effect with the same action ID does not qualify. An invalid
matcher return raises `ValueError`. Matchers are never called for `UNKNOWN`
receipts, so malformed or insufficient source evidence remains uninterpreted.

Supplying the matcher also declares that the agent's `SUCCESS` or `FAILURE`
assessment concerns satisfaction of this action's outcome contract. Known
violations can then be compared with those reports. Known satisfaction requires
an attributable target witness before assessment alignment or a lost-response
diagnosis is claimed. Unknown outcomes, unknown assessments, other-actor state
satisfaction, and unconfirmed origin remain unassessable. Omitting the matcher
is appropriate when the application's assessment has a different meaning.

For known refund results, domain-invalid evidence such as `records: [17]`,
non-integer refund counts, or malformed linked payloads raises `ValueError`.
Unknown receipts can retain malformed source records without interpreting them
as target witnesses. This distinction keeps wire-valid JSON separate from
valid domain evidence.

## Offline artifact example

[examples/artifact_delivery.py](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/examples/artifact_delivery.py)
implements a second domain, `artifact_delivered`, using only the public API and
the Python standard library. It registers a path, content digest, deadline, and
persistence horizon; captures a timeout response and failure assessment;
consumes a separately captured artifact-store snapshot; verifies it; and
round-trips the trace before explaining it. The fixture's digest is computed
from the bytes read back, rather than copied from the requested digest.

Run it from the repository with an installed package:

```console
python examples/artifact_delivery.py
```

The default captured fixture contains the requested artifact with independently
reported action and actor metadata. Its custom matcher qualifies that target,
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
contract. A commit strictly after the horizon is outside its scope. The matcher
qualifies only deadline-eligible revisions with sufficient persistence witnesses;
it does not treat later origin-linked revisions as target matches. Implement and
test other predicates, current-state artifact replacement semantics, or count
semantics explicitly in the application's verifier.
