# Native autonomous controller adapter — 21 October 2026

This is a research wrapper for the pinned tau source revision
`96a3ef92329baf908ffe9dfe188cea34e8701d2a`. It is not a new official benchmark
or an evaluation result. No official task definitions, reference actions,
expected databases, reward criteria, user scenario, or evaluation outcomes were
used to implement or test this adapter. Native public policy, tool bodies,
message classes, and public agent-factory source were inspected. The broader
project has previously exposed the corpus in its separate model-free study;
the new autonomous condition must not be described as an author-unseen holdout.

The source is [controller.py](../research/native_agent/controller.py). Root owns
the prospective protocol, source freeze, hardware/provider gates, evaluation
execution, and final artifact audit. This document does not authorize an
evaluation run or assert that those gates passed. There are no human subjects,
annotation, recruitment, or qualitative human labels in this design. The native
`transfer_to_human_agents` function is retained as an unchanged simulator tool;
its return is simulated and does not contact a person.

## Matched arms and the added classical comparator

| Arm | Native read schedule | Additional interpretation visible to assistant | Fixed guard |
| --- | --- | --- | --- |
| B | Actual public preflight/post-return lookups | Raw native responses and common plain recovery instruction | No |
| C | Same deterministic schedule for each proposed mutation | Classical public-field report computed with standard-library arithmetic | Yes |
| R | Same deterministic schedule | ConsequaX 2.1.1 public-field receipt | No |
| G | Same deterministic schedule | ConsequaX 2.1.1 public-field receipt | Yes |

C was added before any new autonomous evaluation run to provide a stronger
classical comparator. Its controller does not import or call ConsequaX. B also
does not import or call ConsequaX and does not compute a hidden field verdict;
it retains a raw public capture for later auditing. R/G require the selected
installed module to report exactly version 2.1.1. The runner must additionally
verify the exact imported package path and payload hashes; a version string is
insufficient identity evidence. The separate product release 2.1.2 is not the
measured scientific runtime.

C and G use the same explicit application predicate and gate rules. This is an
implementation-conformance and overhead comparator, not independently authored
application semantics. C provides a compact status/reason/origin report; R/G
provide the full serialized field receipt, so model context bytes and tokens
can differ and must be charged. No superiority over the classical arithmetic
is presumed. B/R/G provide the requested receipt/guard ablation, while C/G
exposes whether the framework differs from a capable conventional controller.

Specifically, C and the R/G custom verifier call the exact same `field_status`
helper. C bypasses the package; R/G construct typed actions/observations and
dispatch that application predicate through `cx.verify`. This comparison does
not independently cross-check predicate arithmetic or evaluate the package's
built-in temporal RecordVerifier. Shared predicate errors can survive in both
arms. Task-reward differences can reflect representation, context, framework
dispatch or guard interactions, rather than a different field algorithm.

The complete unchanged native policy and tool set remain available in every
arm. The common additional recovery instruction is constant in source and is
appended after the native system prompt; it does not replace policy. Native
assistant and user instances, task initialization, required DB+COMMUNICATE
grading, strict replay, and shared resource limits belong to the runner and
must remain unchanged across arms.

## Actual read scheduling and intended field predicates

The wrapper never invokes a bound native `Tool`, its function body, an
environment method, or a database. It emits a real `AssistantMessage` containing
a native read `ToolCall`. The unchanged orchestrator executes it and returns a
real native `ToolMessage`; that message remains in the native trajectory and in
the assistant's subsequent model input. The same process emits the pending
mutation, then post-return readbacks. No fabricated successful tool result is
returned for an intercepted proposal or a guard block.

The six native airline writes are covered:

| Mutation | Preflight | Post-return reads | Predicate |
| --- | --- | --- | --- |
| `cancel_reservation` | `get_reservation_details` | Same reservation lookup | Status equals cancelled |
| `update_reservation_baggages` | Reservation lookup | Same reservation lookup | Both requested baggage counts |
| `update_reservation_flights` | Reservation lookup | Same reservation lookup | Cabin and ordered flight-number/date projection |
| `update_reservation_passengers` | Reservation lookup | Same reservation lookup | Exact requested passenger list |
| `send_certificate` | `get_user_details` | Same user lookup | Exactly one new payment mapping, with requested certificate source and amount |
| `book_reservation` | User lookup | Same user lookup, then actual reservation lookup for every newly listed reservation ID | Exactly one new reservation with requested user, route, flight type, cabin, passengers, baggage, insurance, and ordered flight-number/date projection |

Read arguments come only from the proposed mutation payload or newly listed IDs
in a public post-return lookup. A mutation missing its public identity still
reaches the native environment and can produce its genuine native error; the
field contract remains unknown, without an invented preflight read. Native
read errors, non-object responses, identity mismatches, missing fields,
incomplete newly listed reservation details, and unsupported predicates remain
unknown. A false acknowledgement cannot make these predicates satisfied.
Additional native payment effects, fees, seats, ownership/policy correctness,
user intent, task reward, real settlement and long-term durability are outside
these narrow record predicates. Native reward must be reported separately.

The native environment is synchronous and single-threaded for this pilot.
Post-return public reads witness its current returned fields, not an external
provider's causal provenance. Every receipt's origin remains unknown.
Receipt timestamps use actual monotonic milliseconds elapsed since agent
construction. The schema's deadline is the registration horizon; the custom
predicate checks current post-return fields and does not assert delivery by a
deadline, a stability interval, or a safe-to-retry certificate. Native event
indices and nanosecond offsets preserve ordering even when two operations fall
in the same rounded millisecond. There are no illustrative fixed timestamps.

The wrapper refuses a model proposal containing multiple calls when any is a
mutation, recording `unsupported_parallel_mutation` and terminating that slot
with a visible exception for the runner's disposition accounting. It does not
silently serialize parallel mutations or replace a failed slot. Multiple
read-only calls pass through unchanged. This restriction must be frozen and
included in all-slot failure reporting; it must not become an outcome-based
exclusion.

## Conservative guard and its limitations

An operation key is SHA-256 over episode ID, domain, native tool name, and the
canonical complete proposed payload. A transport/model call ID does not change
the key. User turns do not clear it. Every actual mutation dispatch is logged.

C/G prevent any repeated identical dispatched payload, including a prior
violated predicate, because a narrow field violation does not exclude partial
side effects. They also prevent another payload targeting the same public
reservation/user identity while an earlier operation on that resource remains
unknown. A block emits a normal assistant clarification and a separate
`guard_block` record, never a fake tool message or native success.

This rule intentionally has no semantic intent classifier. It can block a
legitimate later operation with an identical payload, and it cannot discover
cross-resource relationships that the payload does not expose. A subsequent
user clarification does not automatically bypass the guard or manufacture a
new intent epoch. Blocks, unresolved histories, affected task success, and
additional dialogue cost must all be reported. No framework-only idempotency,
native provider deduplication, compensation, or cancellation is introduced.
Without natural repeat proposals, guard inactivity is a valid result. No
acknowledgement loss or delayed commit is injected into this native pilot.

## Runner interface and event contract

`make_agent_factory(arm, episode_id, event_sink=None)` returns the public native
factory signature `factory(tools, domain_policy, **kwargs)`. Register it under
a research-specific name using `registry.register_agent_factory`. Factory
`task` and other native auxiliary kwargs are ignored, never inspected. Only
the supplied tools, domain policy, `llm`, and `llm_args` reach the instance.
Create a fresh instance for every arm/episode; no resume or rehydration of
controller state is implemented.

Each instance exposes `agent.events`. A supplied sink receives a deep copy of
each append-only JSON-compatible event so a runner can flush a journal after
every event. An event always includes:

```json
{"schema":"conseqax-native-controller-event-v1","index":0,"arm":"B",
 "episode_id":"declared-run-slot","event":"native_input","monotonic_elapsed_ns":0}
```

The example offset illustrates the schema only; execution records actual
offsets. Event-specific fields are:

- `native_input`: actual `message` serialized from native User/Tool messages.
- `native_emit`: actual emitted native assistant `message`.
- `model_input`: complete `system_messages` and `messages` sent to generation,
  preserving every assistant-visible receipt and raw native response.
- `model_proposal`: unmodified native provider `proposal`, including metadata.
- `read_dispatch`: `phase` (`pre`, `post`, `detail`), `operation_key`, actual `call`.
- `contract`: compiled public field `contract` and `operation_key`.
- `mutation_dispatch`: `operation_key` and actual native `call`.
- `raw_public_capture` (B): operation key, contract, after read and details,
  with no derived verdict.
- `receipt` (C/R/G): serialized `receipt` and boolean `model_visible`.
- `guard_block`: operation key, fixed reason and unmodified suppressed proposal.
- `unsupported_parallel_mutation`: unmodified unsupported proposal.

Native call IDs join each dispatch to its actual native ToolMessage. The
immutable `SimulationRun.messages` is the authority for native replay; events
must agree with that trajectory. Suppressed proposals belong only in controller
events. A clarification preserves the generating proposal's usage/cost metadata,
while its actual native emitted tool-call list is empty. Extra read messages
have no invented generation usage. The harness must still count every actual
assistant/user model request, including a failed request that yields no output,
and charge all actual read calls, context tokens and generated tokens.

Database hashes and side-effect ledgers are evaluator-only runner observations;
the wrapper has no access to them. The separate auditor must reconstruct actual
read/mutation dispatches chronologically and compare native outputs, including
read outputs. Native strict replay alone skips read tools and is insufficient
for this event-contract check. The runner must guard provider/network routing,
context fit, termination caps, native policy/source identity and all evaluation
slots; this adapter does not replace those execution gates.

## Synthetic verification scope

[Unit tests](../tests/test_native_controller.py) use invented public record
fixtures, checking all six predicates, unavailable/identity/missing-field
abstention, pre-existing versus newly created records, duplicate certificate
effects, immutable inputs and stable operation keys. A subprocess uses the
actual pinned native LLMAgent/message classes and installed ConsequaX 2.1.1,
while a synthetic deterministic proposal function replaces model generation.
Socket connection and DNS are blocked and official task-file opens are refused.
It exercises a real preflight-message → mutation-message → postflight-message
cycle in all four arms and their duplicate guards. The test asserts B/C do not
import ConsequaX. These are integration unit fixtures, not live model tool-call
compatibility or autonomous benchmark episodes.
