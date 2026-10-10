# First build: internal integration contract

This file fixes interfaces for the parallel implementation. Python 3.11+, standard-library runtime, src layout. All monetary values are integers in minor units. The initial simulator is a controlled research fixture, not a real payment provider.

## Models (`consequa_x.models`)

Use frozen dataclasses and string enums, with constructor validation and a shared `to_dict(value)` JSON-safe serializer. Each record has `.to_dict()` and the top-level `Trace` has `.from_dict()` / `.to_json()` / `.from_json()`.

- `EventType`: user_input, system_instruction, retrieval, memory_read, agent_decision, action_intent, action_dispatch, tool_response, agent_assessment, external_observation, verification, external_effect.
- `ResponseStatus`: success, error, timeout.
- `AssessmentStatus`: success, failure, partial, unknown.
- `VerificationStatus`: satisfied, violated, unknown.
- `OriginStatus`: confirmed, other_actor, unknown.
- `Event(id: str, trace_id: str, type: EventType, time_ms: int, actor: str | None = None, parent_ids: tuple[str, ...] = (), data: dict = {})`.
- `OutcomeContract(contract_id: str, predicate: str, expected: dict, deadline_ms: int, exact_count: int | None = 1, stability_ms: int = 0)`. Deadline is absolute simulation time. `horizon_ms` property = deadline_ms + stability_ms. Initial predicate is `refund_processed`; expected keys payment_id, amount_minor, currency. The verifier interprets a fixed predicate registry, never eval.
- `Action(action_id: str, trace_id: str, actor: str, name: str, arguments: dict, registered_at_ms: int, contract: OutcomeContract, idempotency_key: str | None = None)`.
- `ToolResponse(attempt_id: str, status: ResponseStatus, time_ms: int, provider_request_id: str, result: dict = {})`.
- `AgentAssessment(status: AssessmentStatus, time_ms: int, evidence_event_ids: tuple[str, ...] = (), rationale: str = '')`.
- `Observation(observation_id: str, source: str, observed_at_ms: int, as_of_ms: int, scope: dict, records: tuple[dict, ...] = (), complete: bool = True, available: bool = True)`. `complete` means exhaustive for declared scope and snapshot watermark, not omniscient world truth. as_of_ms <= observed_at_ms.
- `Evidence(observation_id: str, source: str, as_of_ms: int, details: dict)`.
- `VerificationResult(contract_id: str, status: VerificationStatus, observed_at_ms: int, evidence: tuple[Evidence, ...], origin: OriginStatus = UNKNOWN, effect_ids: tuple[str, ...] = (), attributable_effect_ids: tuple[str, ...] = (), reason: str = '')`.
- `Trace(trace_id: str, action: Action, events: tuple[Event, ...], responses: tuple[ToolResponse, ...], assessment: AgentAssessment, observations: tuple[Observation, ...] = (), verifications: tuple[VerificationResult, ...] = (), schema_version: str = '0.1')`.

Avoid invented global confidence scores. Attribution estimates have their own statistical uncertainty. JSON round-trip must preserve tuple and enum semantics and reject incompatible schema versions/unknown fields.

## Simulator (`consequa_x.benchmark.payments`)

- `Fault`: clean, fail_before_dispatch, timeout_before_commit, timeout_after_commit, false_success, delayed_visibility, partial_effect, duplicate_effect, wrong_parameter, wrong_target.
- `PaymentWorld(payments: dict[str, int] | None = None, currency: str = 'INR', seed: int = 0)`, default payment pay_42 balance 1_000_000 minor units. `time_ms` property starts at 0; `advance(milliseconds)` is monotonic; `snapshot()` returns isolated snapshot and `fork()` returns independent world.
- `refund(action: Action, attempt_id: str, fault: Fault = Fault.CLEAN) -> ToolResponse`.
- `read_refunds(payment_id: str, *, lag_ms: int = 0, include_provenance: bool = True, available: bool = True) -> Observation`.
- `external_refund(payment_id: str, amount_minor: int, actor: str = 'external_operator') -> str` returns effect id.
- `reverse(effect_id: str) -> None` is synthetic compensation, logged; no claim that real Razorpay refunds can be reversed.
- `ground_truth` property is a copy of evaluator-only JSON records. Never pass it to verification/graph/explanation.

Readback records contain effect_id, payment_id, amount_minor, currency, committed_at_ms, status; optionally action_id, attempt_id, actor. Retain reversed_at_ms for horizon evaluation. Missing provenance must yield uncertainty, not inferred origin. Delayed visibility can be modeled by a source-wide declared lag/watermark; do not reveal whether a hidden missing effect exists through `complete`.

Stable idempotency keys reject changed payloads and prevent repeat effects. Distinguish logical action, execution attempt, and provider effect identifiers. Enforce finite refundable balance; unsafe duplicates are partial refunds that fit within the original balance.

## Attribution (`consequa_x.attribution`)

Implement independent of simulator: `ReplayRunner` protocol `run(intervention: Intervention | None, seed: int) -> ReplayOutcome`.

- `Intervention(event_id: str, kind: str = 'neutralize', replacement: object = None)`; reject unsupported kinds, no arbitrary malformed history deletion.
- `ReplayOutcome(action_selected: bool, consequence_satisfied: bool | None)`.
- `EffectEstimate(event_id, target, baseline_rate, intervention_rate, effect, confidence_interval: tuple[float,float], samples, seeds: tuple[int,...], unknown_pairs: int = 0)`.
- `leave_one_out(runner, interventions, *, samples=20, seed=0, target='consequence') -> tuple[EffectEstimate,...]`. Valid targets action/consequence. Require >=2 samples, use paired seed schedule, unknown outcomes cannot become failures. Unknown consequence pairs cause a clearly documented refusal to estimate (do not silently condition estimates on known pairs). Return a conservative Wilson/Newcombe difference interval or comparably defensible stdlib interval. Do not claim iid samples measure generalization.
- `recency_attribution(events, *, before_ms: int) -> str | None` reports heuristic candidate event id, not a causal score; only context types before the decision.

## Parent-owned modules

`verification.py`: read-only verifier uses Observation only, validates fixed refund contract, refuses absent outcomes before the contract horizon/watermark or in unavailable/incomplete/wrong-scope views. Evaluate effect committed by deadline and status through horizon; origin is separate from state satisfaction.

`graph.py`: typed nodes/edges with temporal/dependency/response/effect/verification/evidence links. No causal attribution links without experimental estimates. Build only from trace plus readback evidence, never gold logs.

`explanation.py`: reported assessment vs verified result; multi-label diagnoses; unknown outcome does not prove belief error; no runtime replay.

`benchmark/runner.py`: fixture policies, typed context interventions, isolated worlds, factual scenarios, paired full-world replay. `cli.py`: offline demo and experiment exports, truth files separated from explainable trace files.

Root packaging, README, docs, schemas, demo outputs and integration tests are parent-owned unless reassigned.
