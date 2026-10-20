# Prospective recovery application world

This is a newly authored, **AI-assisted held-out research suite**, authored by a
separately delegated AI agent. It is not independently human-authored. The author
read the public 2.1.1 `RecordVerifier` and model conventions, and did not read
controller implementation, earlier study outputs, paper results, or prospective
study results. No held-out episodes or model runs were executed during world
development. Synthetic unit-test fixtures are separate from the held-out corpus.

The corpus contains 24 tasks in 12 scenario families, with two parameter variants
per family. It spans inventory reservation, support-ticket transition, and
artifact/delivery registration. Variants and repeated seeds are dependent
observations within a family; they do not increase the family-level inference
sample size. Task identifiers describe workflows and do not reveal mechanisms.
Authorship separation limits direct adaptation to controller code; it does not
establish independence from shared model priors or eliminate design bias.

## Public boundary

`World(case, seed: int, db_path: Path)` creates a fresh SQLite file. Existing
files are rejected. Call `close()` or use the context manager. The database and
`_world` configuration are evaluator-only. `public_case(case)` allowlists the
task request and declared capabilities; `load_cases()` is an evaluator helper.
No simulator module imports the framework or a controller.

The public case contains `case_id`, `family_id`, `domain`, `operation_id`,
`actor`, `initial_at_ms`, `payload`, `target`, `scope_fields`, `scope`,
`native_idempotency`, `deadline_ms`, `stability_ms`, `recovery_deadline_ms`, and
`safety_horizon_ms`. `target` contains `predicate: "record_present"`, an exact
`expected` business-field mapping, and `exact_count`. The runner supplies a
contract identifier and the separately declared deadline and stability fields
when constructing a framework contract.

`dispatch(operation_id, actor, at_ms)` returns:

```json
{
  "status": "success|timeout|error",
  "response_at_ms": 0,
  "attempt_id": "<operation_id>:attempt-<one-based dispatch number>",
  "result": {"code": "accepted|transport_timeout|request_failed|identity_conflict"}
}
```

An optional top-level `terminal_not_committed: true` is an application-issued,
attempt-scoped provider guarantee: that specific attempt has terminated without
an effect and can never commit. It is never attached to an attempt with a
scheduled commit, and is suppressed when replaying earlier native-idempotent
work. It says nothing about earlier attempts or future retries. An ordinary
timeout, a successful acknowledgement, an exhaustive empty snapshot, or a
source watermark supplies no such guarantee. The response never reports hidden
commit status or hidden pending-work state. Stable logical identity and actor
are enforced across retries; a different identity or actor is rejected.

`readback(at_ms)` returns precisely the public Observation JSON keys:

```json
{
  "observation_id": "...",
  "source": "sqlite-application-ledger/v1",
  "observed_at_ms": 0,
  "as_of_ms": 0,
  "scope": {},
  "records": [],
  "complete": true,
  "available": true
}
```

Each record has `effect_id`, `committed_at_ms`, domain business fields, optional
`removed_at_ms`, and only the origin audit fields actually retained by the
application: `action_id`, `actor`, and `attempt_id`. Origin fields may be missing;
they are never fabricated or relabeled. True causal columns are separate and
are excluded from every public response and observation. Externally produced
state has its actual external actor and logical identity, subject to the same
honest audit omissions. A matching external record can satisfy an outcome
without establishing this agent's contribution.

The `source_receipt` property declares source admission, application ownership,
target scope, the authoritative relative commit clock, lifecycle-history and
watermark meanings, provenance semantics, native idempotency, and provider
resolution semantics. These declarations are issued by the application adapter,
not accepted from arbitrary text in records. The runner must admit this trusted
adapter once and must not treat a foreign source's self-declared trust as
authenticated evidence. Per-observation availability, completeness, scope and
watermark still constrain every use of this source.

## Actual application state and time

The simulator uses Python's standard SQLite binding and no external services.
`effects` records actual committed lifecycle history and separate reported and
causal provenance. `pending_events` stores commit/removal work. `idempotency`
reserves native keys before a commit, so an in-flight retry cannot schedule a
second effect for the same operation. Unsupported idempotency creates a fresh
request on every accepted retry. A successful acknowledgement can lack any
effect; a timeout can precede or follow a real effect.

Inventory commits create `inventory_reservations` and atomically deduct real
`inventory_stock`; a release restores stock. Capacity rejection creates no
reservation. Ticket commits create `ticket_transitions` and update
`support_tickets`; a different status or queue supersedes prior active state
certificates, preserving removal tombstones. Identical repeated transitions
remain separate execution records. Delivery commits create
`delivery_registrations`; revocation changes their state and preserves history.
These are deliberately small application schemas, not transport-only mocks.

`advance(at_ms)` applies every due event in timestamp/insertion order and commits
the SQLite transaction. Public calls advance to their invocation time; returned
response times do not implicitly advance the world. The runner must schedule
later invocations accordingly. Time cannot move backward. Events at a shared
timestamp are all applied before a snapshot. Counts apply simultaneous changes
together, matching the public verifier's closed deadline-to-horizon interval.

Readbacks query committed SQLite history through the declared watermark.
Cached views disclose their actual older `as_of_ms`. Removals are shown only
after that watermark reaches their time. Unavailable sources return no records
with `available: false` and `complete: false`. Pagination and active-only views
always declare `complete: false`; an active-only view cannot attest lifecycle
stability. Partial scope is reported as its actual query scope. Audit omissions
are source limitations, not invented provenance. No readback reaches into
`truth()` or adds future facts.

Seeded variation is limited to legitimate bounded exogenous-event timing.
Timing uses a hash of the seed and external event identity, so policy-dependent
random draws cannot change an unrelated external schedule. Seeds do not choose
success labels, values, actors, failure modes, or controller behavior. No
mechanism branches on case names, policy names, controller observations, or
future evaluation results.

## Evaluation receipt and limits

`truth(at_ms)` advances the same application and returns evaluator-only state.
`target_satisfied` evaluates the original deadline and stability horizon;
`linked_target_satisfied` additionally requires the correct causal action and
actor. Both are `null` until the original horizon is reached. Exact count means
the required number of correct records committed on time and continuously
present through the horizon, with no transient excess matching count during
that closed interval.

`eventual_recovery_satisfied` evaluates correct records committed by the public
recovery deadline and continuously present through the public safety horizon;
`linked_recovery_satisfied` additionally requires genuine causal linkage.
These are `null` before the safety horizon. Recovery never rewrites the original
SLA result. `duplicate_count` counts own execution records beyond the permitted
count through the safety horizon, including removed effects;
`sla_duplicate_count` is the analogous count within the original horizon.
`own_unwanted_effect_count` counts wrong-value own records and own records
committed after the recovery deadline. Reversed effects, causal records,
dispatch/readback call logs, committed/rejected/reversed effect counts, native
replays, returned-record counts and pending-event counts remain visible only to
the evaluator. Metrics count actual application interactions and side effects.

The original horizon must precede or equal the recovery deadline, which must
precede or equal the safety horizon. These are bounded observation/evaluation
windows; reaching any horizon does not prove a provider has no future work.
Pending work is not admitted to controllers. `source_receipt` documents source
scope and clocks, not universal finality. Runs that stop earlier cannot be
silently scored as stable. Preserve all failures and unknown outcomes, and
report original SLA, eventual recovery, attribution, unwanted effects and
duplicates separately.

Matched controllers must receive identical admitted captures at identical
query times when testing evidence interpretation. The application itself is
causal: different dispatch histories can produce different later state. The
runner must distinguish identical-capture comparisons from live recovery
rollouts, rather than forcing state equality by hiding actual writes. Identical
case, seed, dispatch history and query schedule produce identical public JSON.

This suite is a small synthetic, finite-horizon application study. It does not
establish production reliability, general agent competence, adversarial source
authentication, unbounded finality, or causal benefit outside the declared
application and evidence boundary. Public source admission and attempt-level
provider resolution are substantive assumptions, not capabilities inferred by
the record verifier.

## Prospective handling

Before any held-out execution, commit/hash-bind the corpus, world source,
controller/protocol source and evaluation plan together. Seal hashes before
opening the corpus to the controller developer. Keep development tests on
separate synthetic fixtures. No GitHub Actions, site/package/workflow changes,
staging, or commits are performed by this world-authoring task. Revisions after
the prospective freeze require an explicit version change and disclosed reason;
never replace a difficult case after inspecting its result.
