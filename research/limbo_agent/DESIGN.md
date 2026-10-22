# Prospective LIMBO adapter design

21 October 2026. Feasibility and public API inventory only. This is a possible
later complement to the active Tau airline pilot; it neither replaces nor
amends that pilot. No LIMBO model request, task episode, production service
request, dependency installation or participant review has been performed.

## Exact source and inspection boundary

Author repository: <https://github.com/jaxblack/limbo-bench>. The separate local
checkout `D:/ConsequaX-Research/limbo-pinned-2db09fba` is detached at
`2db09fba22a0572a70639162a808906409f612a8`. It was cloned with blob filtering and
no initial checkout, then sparsely checked out. The allowlist is README,
LICENSE, DATA_LICENSE, requirements.txt, `limbo/__init__.py`, and the public
`llm.py`, `agent.py`, `runtime.py`, `grader.py`, `policies.py` and `runner.py`.
No task-definition file, fixture, archive, episode record or case-study file
was opened. No upstream Python module was imported. The three public schema
declarations `VerifyResult`, `Contract` and `ToolSpec` in `services.py` were
additionally inspected through declaration metadata only; service handler and
verifier bodies and actual domain/task instance values were outside scope.
The upstream source is unchanged.

`preflight.py` repeats read-only Git identity and source-byte checks, extracts
public signatures with AST, and inventories installed distribution metadata.
Git lazy fetching is disabled during this preflight. Its retained result is
`identity-preflight-2026-10-21.json`; it binds all eleven allowlisted files,
the public schema source, and the preflight source itself. LF/CRLF checkout
conversion is accepted explicitly, and immutable Git and actual file hashes
are recorded separately. The following SHA-256 values refer to Git blob bytes:

| Source | SHA-256 |
| --- | --- |
| `limbo/agent.py` | `c145bc4c32050fa0446f061aa6c300a8e178c186dcc8cc180ba028b7dc47d672` |
| `limbo/runtime.py` | `241a21b60fd41deced45354d2c5565df399bc25e48c292acce1e1fafb25846ad` |
| `limbo/grader.py` | `77ea82d94e8a3339538b23824f4ed2babd35edd186d5129de87bc5bff4f90b99` |
| `limbo/policies.py` | `63075898473ef729020cbe3b176325958ed7eb3212e8b4927fb0461ef00e72f8` |
| `limbo/llm.py` | `a394cb8bc6777ea94c1e5071f690c6b3e49e1e74626cb389d494ab0e458dd464` |
| `limbo/runner.py` | `f6790f8ea20d2c0421e061f710c72896e6aeecb2c2a09044a526bf9a8bbb50bc` |
| `limbo/services.py`, schema declarations only | `68483bbfbfed20b422627850ee6f73edd947c6487810e838da5fab59b4dcb906` |

Code is MIT; released episode records and generated tables/figures have a
separate CC BY 4.0 license. No released record archive was downloaded.

## Native APIs and the narrow adapter seam

The unchanged public entry point is `agent.run_episode(spec, client=...)`
(`agent.py:78`). `EpisodeSpec` declares task/template metadata, fault mode,
policy, model, tool-call cap, contract variant and `human_available`. The native
runner builds the task/world/fault plan, creates a policy through its imported
`make_policy(spec.policy, spec.episode_id)` name, runs the agent loop, settles
pending effects with `rt.flush()`, and invokes the native grader.

The policy extension point is `Policy.execute(rt, name, args)`
(`policies.py:73`), returning the actual observation dictionary. There is no
public policy-registration API or policy argument to `run_episode`. A later
frozen launcher can temporarily replace **only** `limbo.agent.make_policy`
with a scoped factory that delegates every native policy name to the original
factory and supplies the package condition for one new registered study name.
Restore it in `finally`; use one subprocess per episode and no threads. This
is an explicit in-process extension of the public dispatch seam, not an
unchanged stock CLI. The factory receives only a condition name and opaque
episode ID, never `TaskInstance`, targets, focal matches or a fault plan.

`ToolRuntime.execute(name, args, source="agent", note="")`
(`runtime.py:249`) dispatches actual tools and records `ToolEvent` entries.
An observation is either an actual success such as `{ok: true, result: ...}`
or an actual error `{ok: false, error: {type, status?, message?, ...}}`.
An uncertain timeout is an error observation, not proof that no effect exists.
The model sees the unchanged native `observation_text` serialization.
Guard-suppressed calls must be recorded as native policy interventions;
they are never counted as dispatched writes or fabricated service replies.

Public verification is a distinct API:
`rt.verify(name, args, t_call, truth=False)` (`runtime.py:390`). Its declared
return type is `VerifyResult(status: str, detail: dict[str, Any])`
(`services.py:66`). Native policies recognize `found`, `absent`, `partial`
and `unverifiable`; the pending controller state additionally uses `unknown`.
Partial-batch handling reads `detail.get("missing_rows")`. No general request
ID, provenance proof or uniform record schema is promised by this declaration.
The exact per-domain result shapes remain unvalidated. `truth=True` is
privileged and must be refused before dispatch for every measured condition.

Contracts declare `write`, `idempotent`, `destructive`, `irreversible`,
`supports_key(args)`, `identity(args)`, `visibility_sla(args)`, optional batch
field/compensator/drift, and a verifier callback. `ToolSpec` also declares the
public tool name/domain/schema/description and latency. The adapter must not
hand the framework a raw `ToolSpec`: its handler/verifier callbacks and the
runtime expose evaluator state.

## Public-information boundary and package receipt semantics

Keep world construction, fault scheduling, task targets and native grading in
the trusted runner. Give the framework a small copied input object: current
proposed tool name/arguments, prior actual observation, relevant public contract
metadata, public verification status/detail, and timestamps. Permit explicit
copying of public instruction/tool schemas only when needed. Never supply
`task.targets`, `task.summary()`, `focal.match`, `fault_truth`, fault logs,
pending requests, entity collections, the ledger, effect IDs or native grade.
The native result contains many of these fields after execution; it is an
evaluator artifact and must not be recycled into subsequent policy inputs.

A capability-limited runtime view should delegate real `execute` and
`verify(..., truth=False)` calls and expose only contract metadata, a scalar
virtual clock, an audited virtual wait, and the previous dispatch start time.
It must not generically forward attributes. Tool event views expose timestamps
only, excluding fault/effect fields. Trusted contract callbacks may compute
identity/key support/declared visibility from the public payload, but raw
callbacks and world references do not enter framework inputs. Record every
boundary input so an independent audit can check this information firewall.
This is a trusted-code access boundary; do not call it an OS sandbox.

The first integration should add ConseqaX 2.1.1 current-public-evidence receipts
to the same conservative decision rule as the strong native guard. Native
`found` is evidence of a matching visible effect, not proven ownership by the
current request; origin remains unknown unless a public API supplies a binding.
Native `absent` is a statement about the current read path, not a guarantee that
an in-flight write cannot commit later. A visibility SLA does not bound delivery
or execution latency. Preserve `partial` and `unverifiable` explicitly; do not
coerce them into completed/failed. Package receipts must not claim end-to-end
deadline, durable settlement or exactly-once execution merely from a verifier
status. Actual native grader results remain separate from receipt predicates.

## Strong native comparisons and comparable work

The strongest nonprivileged supplied comparator is `make_policy("guard", id)`
(`policies.py:306`): native idempotency-key insertion where supported,
consistency-aware verification, partial-batch recovery, conservative blocking
of unverifiable repeats, and model-visible annotations. Preserve it unchanged.
Its `prompt_variant` inherits the normal policy prompt. `vbr`, error-code
`rules` and `sdk_retry3` can explain components; they cannot replace the strong
guard comparator. `waitN` is a separately declared assumed in-flight bound,
not an empirically valid bound on heavy tails. Freeze any N before collection.
Exclude `oracle` and `outcome_oracle` from deployable comparisons: both use
privileged truth, and the latter additionally reads pending work.

Native intent matching uses `same_intent`, including similarity for long text,
rather than strict payload equality. Its active pending statuses and one-time
suppression semantics are part of the reference method. A matched package
condition should reuse this rule or label any altered matcher as an additional
intervention. Give both arms identical public reads, key support, contract,
prompt opportunities, waits and attempt ceilings. Start with native contracts;
`keys_everywhere` changes provider capabilities and must be paired across arms.
If receipts preserve the native guard's decisions, action/outcome parity is
the expected conformance result, not algorithmic superiority.

Count automatic work. `run_episode` caps proposed agent tool calls, whereas
native policy retries can invoke extra `rt.execute` calls. Native `verify`
does not append a `ToolEvent` at its boundary; direct `world.advance` waits
also need a separate journal. Instrument real execute/verify/wait boundaries
and record source, arguments, public result, virtual start/end and wall time.
Retain native runtime events separately, including late commits. Verification
is a contract-routed simulator abstraction, not necessarily a model-issued
ordinary read or an independently operated service. Its per-domain latency and
cost require later validation; do not assume it is free or equal to one read.

## Native grading and what it proves

Keep `grader.grade(task, world)` unchanged (`grader.py:145`) and settle pending
effects exactly as upstream does before grading. Report native `TS`, `EOS`,
`clean_success`, `exact_state`, executed/live/compensated duplicates,
collateral changes, extraneous writes and total effects separately.
`TS` means all target minimums are met and no graded collateral change exists.
`EOS = TS and dup_executed == 0`; it does not additionally require zero
`extraneous_writes` or `exact_state`. `exact_state` checks only whether each
target's final live count equals its expected count; it ignores collateral and
extraneous writes and is not equality of the complete world state.
`clean_success = TS and dup_live == 0` (`grader.py:162–177`).

The executed/duplicate metrics need domain qualifications. `_effect_matches`
has no status-target branch, so status `executed` is always zero; repeated
status writes therefore cannot raise native `dup_executed`. Upsert execution
counts include matching `CREATE` effects for the table/key, then are capped at
the final matching live count. Refund execution counts are explicitly not
capped this way (`grader.py:38–68,149–158`). These adjustments can discard
historical effects from the reported execution count. `dup_compensated` is the
derived value `max(0, dup_executed - dup_live)`, not a separate count of
compensation calls. None of these fields is a universal physical-execution
counter. Preserve the original domain-qualified native metrics; do not relabel
EOS as a general exactly-once guarantee. Any stricter conjunction must be
separately named, prospectively specified, and reported alongside them.

Native event records include effect IDs and fault labels and are evaluator-only.
An independent replay must compare all actual execute/verify/wait boundaries,
the virtual clock, delayed settling, final world/ledger and every native grade
field. Authored implementation inspection alone is not replay validation.

## Local transport and automated-only execution

The minimal public provider client is standard library Python. Instantiate
upstream `LLMClient` with `protocol="chat"`, the actual local model tag,
temperature 0, declared output cap/timeouts, `max_attempts=1` and
`concurrency=1`. Set a numeric loopback `LIMBO_BASE_URL` and nonsecret dummy
`LIMBO_API_KEY` in the episode child only; clear extra headers, proxies and
hosted credentials. The native chat path constructs `/chat/completions`
directly through `urllib.request`, so the existing Tau httpx hook cannot be
assumed to guard it. A new audited urllib boundary must restrict the exact
endpoint/model, refuse redirects/cloud traffic, preserve full schemas/history,
and perform exact live render/tokenizer context checks before each send.

The native chat constructor does not expose or send a model seed. Do not claim
a requested fixed seed or deterministic generations without a disclosed,
prospectively frozen transport extension. Preserve raw request/response bodies
and failed-send accounting; native missing usage becomes zero and needs an
external availability flag. `max_attempts=1` prevents its HTTP retry loop from
sending twice, although `_post` still sleeps after its final failure. Validate
that behavior with invented offline fixtures before any model call. Enforce
an external combined model-invocation limit, actual tool/verify/wait ceilings,
and hard parent deadline. Fix all ceilings before official collection.

Use the unchanged `run_episode` under a serial, one-shot launcher, not stock
`runner.run`: the stock CLI defaults to eight workers and resumes/retries error
records on another run. Freeze the complete paired schedule and source/runtime
identities first; preserve every planned failure/unstarted slot with no
replacement. Set `human_available=False` in every condition. This disables the
simulated operator; no person is involved. Operator attempts can still advance
the virtual clock and fail, so retain them in costs. No hosted API, GitHub
Action, participant label or real external-service write is needed.

## Remaining gates

The local metadata preflight passed at the pinned source. The native Python
environment has ConseqaX 2.1.1; some optional plotting/statistical dependencies
are absent. Core modules were not imported, so this is not an execution or
dependency-import proof. No package was installed for this assessment.

Before implementing or claiming benchmark results: validate allowed per-domain
verification shapes and costs without inspecting task targets; build and test
the capability boundary and unchanged native guard parity on invented worlds;
add complete execute/verify/wait and HTTP failure accounting; prove local tool
roundtrip/context preservation and resource limits; freeze selection using
metadata-only evaluator extraction; then freeze source/protocol and run the
first-attempt matrix with independent native replay. Current source selection,
adapter control law, budgets and model capability remain design decisions.
This source assessment establishes neither comparative performance nor
top-conference readiness.
