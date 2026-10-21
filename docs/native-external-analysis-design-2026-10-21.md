# Native autonomous external pilot: analysis and independent audit

Status: prospective analysis and audit design, 21 October 2026. No official
evaluation episode or model call was executed for this document. This review
inspected public native implementation code and the prior feasibility document;
it did not inspect official task scenarios, reference actions or expected gold
databases. GitHub Actions remain disabled. Human labels are not required by this
automated pilot and no human-validation result is implied.

## Estimand and exposed benchmark corpus

Use the unmodified maintained benchmark at
`96a3ef92329baf908ffe9dfe188cea34e8701d2a` (tau3 branding, Python package tau2
1.0.1). The first autonomous pilot consists of 12 prespecified airline IDs:
`7,23,18,11,14,3` from the nonempty communication stratum and
`45,32,39,15,30,44` from the empty communication stratum. Selection and exclusion
rules are in [the preceding feasibility design](native-agent-validation-design-2026-10-20.md).
All selected tasks require the native DB and COMMUNICATE reward components;
the first pilot does not require a hosted LLM judge. Empty communication
requirements produce the native vacuous result, and must be reported separately
from substantive communication checks. Do not add optional experimental NL
assertions or claim that unrequired NL assertions were evaluated.

Before any evaluation generation, freeze four conditions, B/R/C/G, on the same
12 tasks and same declared seed(s). With one seed this is **48 planned slots on
12 distinct tasks**, not 48 independent tasks. B is a raw-public-readback
controller with the common recovery instruction and no derived field verdict.
R adds public-field contract reporting to the same read schedule. C and G receive the
same allowed native pre/post reads and deterministic dispatch guard. C calls
the shared standard-library field predicate directly; R/G call that same
predicate through a ConseqaX custom verifier. This tests receipt integration
and representation, rather than independently implemented verification logic.
Exact prompts, ceilings, ordering, arguments and compiler behavior belong in
the committed execution protocol. C/G equality is observed conformance,
not evidence from an equivalence design or proof of framework superiority. R/G need
not realize identical dialogues or observations after different actions.

The assistant and dynamic user remain native autonomous model roles. Preserve
the complete domain policy and real model-emitted structured tool calls. No
reference-action replay or fixed scripted user may replace them. The local
model and user simulator share a model family; they are not independent human
judgments. The native task's user scenario is available only to the native user
simulator and evaluator, never the assistant or contract compiler. The
evaluation criterion and gold actions remain evaluator-only.

All 50 airline and 114 retail task definitions were exposed to adapter authors
in the earlier model-free state-transfer experiment. This prospective pilot is
a new autonomous execution condition on an exposed corpus. It is not an
author-unseen holdout or an independent new task collection. The 12 IDs are a
small deliberately stratified exploratory sample, not a representative
benchmark or leaderboard estimate. No task-population confidence interval,
bootstrap or population significance claim is justified by the 48 slots.

## Preserve the native reward, including native failures

The native entry point is
`tau2.runner.simulation.run_simulation(orchestrator,
evaluation_type=EvaluationType.ALL, env_kwargs=None)`. It attaches the result of
`tau2.evaluator.evaluator.evaluate_simulation` to the returned `SimulationRun`.
For saved text simulations, the unchanged evaluation API is:

```python
evaluate_simulation(
    simulation=saved_simulation,
    task=official_task,  # evaluator-only access after collection
    evaluation_type=EvaluationType.ALL,
    solo_mode=False,
    domain="airline",
    mode=CommunicationMode.HALF_DUPLEX,
    env_kwargs=None,
    strict_replay=True,
)
```

At this revision, only `agent_stop` and `user_stop` receive ordinary component
grading. Every other native termination returns reward 0 with `reward_basis=None`
and no DB/communication component results. Record the original task's required
basis separately so that this native early return does not erase the task
requirements. Retain the native termination, reward object and all diagnostics;
the missing component outcomes are **unavailable**, not component failure or
success. Do not regrade a premature termination as if it terminated normally.

The primary finite-pilot summary is native full-required-reward success over
**all planned slots** in each condition. Native premature terminations, harness
errors and unstarted slots contribute zero operational success. Preserve their
distinct dispositions. A harness error without a native `SimulationRun` has no
invented native reward object: its operational contribution is zero and its
native reward/components remain unavailable. No failed or unstarted slot may
be dropped, replaced, retried or silently resumed. A separately disclosed new
protocol is needed for a repaired repeat. Count completion, normal termination,
premature termination, infrastructure error and unstarted dispositions.

For normally terminated airline tasks, `EvaluationType.ALL` invokes the native
environment, action-diagnostic and communication evaluators. Only the required
DB and COMMUNICATE components multiply into reward. Preserve all component
objects, required-basis entries and native action checks, including diagnostic
checks outside the required basis. Action-reference similarity is not the task
success criterion. No optional conversation-review model is required.

`EnvironmentEvaluator.calculate_reward` constructs a fresh predicted native
environment, applies official initialization and replays the actual full
trajectory with `strict=True`. A separately constructed gold environment runs
the official reference actions **inside the evaluator only**. It compares both
agent and user database hashes. The current-field contract, native full-task
end-state equality and action-linked origin are different targets. A correct
requested field does not imply that the full task or all policy obligations
were satisfied; the full native reward is never replaced by a verifier receipt.

The native communication evaluator performs case-insensitive required-substring
matching against assistant text after removing commas. It is a narrow automated
criterion, not a general judgment of explanation quality, instruction following
or helpfulness. Report nonempty/empty strata and exact numerators/denominators.

## Full chronological replay is necessary in addition to strict native grading

An important source-level limitation is retained unchanged:
`Environment.set_state(strict=True)` validates call/result ordering and IDs and
replays mutating tools, but deliberately **skips nonmutating reads/thinks**. It
also skips unknown tool names as no-op hallucinations. Thus a passed native
strict replay does not independently authenticate the contents, number or cost
of added verifier readbacks. The audit must do both of the following:

1. Regrade the saved native `SimulationRun` through the unchanged full-required
   evaluator with strict replay enabled.
2. Independently reconstruct every actual episode tool call in chronological
   order, including reads, thinks, unknown calls and mutating calls. Compare its
   fresh native response and before/after database hashes against the retained
   evaluator-only call journal and native transcript.

Instrumentation wraps the actual live environment externally; no upstream
method body or benchmark task is edited. The wrapper/assistant does not receive
privileged database hashes, snapshots, gold, criterion data or mutation diffs.
Every wrapper-induced read is an actual native tool call and result in the
native transcript, charged against the same declared interaction ceilings.
Suppression yields an ordinary assistant clarification or abstention, not a
fabricated successful tool result. No fault injection is introduced in this
first pilot.

The evaluator-only episode call journal uses the following proposed schema,
to be fixed exactly in the execution protocol before collection:

```text
call_index: zero-based consecutive integer
request: {tool_name, requestor, arguments}
before: {agent_db_hash, user_db_hash}
outcome: {status: "returned", content: native Environment.to_json_str(actual_result)}
     or {status: "raised", error_type: type(exception).__name__, error: str(exception)}
after: {agent_db_hash, user_db_hash}
```

The hash phase is immediately before/after `make_tool_call`, before the outer
native `get_response` performs its success-only `sync_tools`. Chronological
replay reproduces that order, compares the native serialized outcome, then
performs the same success-only synchronization and checks the native
`ToolMessage` ID, requestor, error flag and structurally decoded content. A
returned `{"error": ...}` value is not conflated with a raised exception.
Root instrumentation may add separately bound compact mutation diffs and wall
timestamps; these diagnostics do not replace hash checks or establish causal
origin. The final schema and phase must be documented if the implementation
uses a different instrumentation boundary.

Native full trajectories include `task.initial_state.message_history`.
Initialization must be captured as a separate phase or excluded consistently
from episode journaling. An auditor first initializes a fresh environment with
the official initialization data/actions/history, compares the retained
post-initialization hashes, checks the initial transcript prefix by semantic
message fields, then replays the episode suffix. It must not apply that prefix
twice. A trailing proposal without a result after a premature termination is
retained as pending, not counted as an executed call. Known completed calls
before that termination can still be replayed as diagnostics without changing
the native reward or filling missing native component results.

## Artifact and audit independence

Freeze the complete ordered 48-slot schedule, source commit/origin, unchanged
native source/data bindings, dependency lock, exact interpreter, installed
framework, original/tagged model digests, context settings, seed, prompts,
ceilings and task ID/criterion-presence manifest before execution. Retain every
attempted model request/response and usage record, each native simulation,
wrapper event stream, call journal, evaluator results, initial/final snapshots
and all failed/unstarted dispositions. Bind all artifacts by an exact inventory
and completion receipt; a partial collection remains explicitly partial.

The independent saved-artifact auditor must not import the research wrapper,
model transport or collection runner, and must not invoke generation. It may
load hash-bound unchanged native environment/data-model/evaluator code solely
for offline replay and regrading. Normal upstream initializers import provider
definitions transitively; that fact is not permission to call a provider.
Run replay/regrading in a fresh process with network calls refused, no optional
review model, and an explicit airline DB+COMMUNICATE basis check before grading.
Any unexpected required judge component must stop the audit, not trigger a paid
or local judge request. Validate imported native code origins and exact source
bytes; do not monkeypatch evaluator logic or disable strict replay.

Windows checkout line endings are a separate provenance issue: a Git-clean
checkout can contain CRLF bytes while its immutable Git blobs use LF. Source
verification may accept only exact Git bytes or a pure LF-to-CRLF checkout
conversion, recording both actual runtime and Git hashes/lengths and the
explicit checkout mode. It must reject all other changes. The execution
protocol still binds the actual runtime source, data and policy bytes; this
rule does not permit modified evaluator code or substituted task data.

The independent auditor implementation may be written by another AI agent in
the same project. This is code independence, not independent human replication.
Automated audit cannot establish absence of all author bias, corpus exposure,
benchmark limitations or local-model failure modes.

## Required finite-pilot tables and interpretation

For every arm and all planned tasks report native operational success,
completed/normal/premature/error/unstarted counts, native required reward and
each component's observed/unavailable counts. Retain all per-task paired
contrasts B/R/C/G, including C/G equality or disagreement and each stratum.
Report native end-state equality and immediate field-contract results in
separate columns. Since native records do not generally authenticate the
current invocation's causal origin or lifecycle interval, preserve unknown
origin and temporal evidence rather than manufacturing a this-action claim.

Side-effect and cost reporting includes actual tool dispatches classified by
native tool type and mutation flag, successful/errored native calls, extra
pre/post reads, proposed versus suppressed writes, consecutive repeated
requests, database changes and final native hashes. A repeated payload is a
request-level diagnostic; it is not proof of a duplicate harmful business
effect. A changed database or compact diff is not proof that a requested effect
was policy-compliant, unwanted, or caused solely by this invocation.

Report assistant and user model request counts, provider-recorded prompt and
completion tokens, unavailable usage, generation errors, latency and charged
tool reads. Native `SimulationRun.agent_cost`/`user_cost` can be null if any
message lacks cost. Preserve that null; local API price zero is not zero
compute cost. Wrapper-generated messages or deterministic dispatches must not
be counted as fresh LLM generations. Raw transport records, rather than
message count alone, determine attempted model calls. No speed or token-cost
claim may omit failed requests or setup/context limitations.

The first pilot adds real autonomous execution and complete required native
grading on this declared subset. It does not alone establish a full benchmark
score, broad generalization, novel formal guarantees, human validity or
top-conference readiness. Negative or null outcomes remain paper results.

Free-form assistant claims are not independently labeled in this automated
pilot. A keyword such as "success" is not an objective unsupported-claim label.
Do not invent a human/LLM claim-accuracy endpoint. Report complete JSON receipt
validity, immediate field counts and the native required reward separately;
semantic accuracy of unrestricted assistant prose remains unimplemented and
unavailable. Raw new booking, certificate and payment entries may be counted as
database observations. Repeated same-argument mutating dispatches and blocked
proposals are request-level diagnostics, not proven duplicate goals or harm.

## Verified native source pointers

- `src/tau2/runner/simulation.py`: `run_simulation`, lines 19-85.
- `src/tau2/evaluator/evaluator.py`: `evaluate_simulation`, lines 88-131
  (premature termination) and 196-278 (ALL and required-basis product).
- `src/tau2/evaluator/evaluator_env.py`: lines 85-129 (strict predicted replay,
  gold-only evaluation path and both DB hashes).
- `src/tau2/evaluator/evaluator_communicate.py`: lines 13-85 (empty requirement,
  native substring criterion).
- `src/tau2/environment/environment.py`: lines 293-409 (mutating-only native
  replay) and 464 onward (`get_response`, error and synchronization semantics).
- `src/tau2/data_model/simulation.py`: `TerminationReason`, `RewardInfo` and
  `SimulationRun`; `src/tau2/data_model/message.py`: native call/result types,
  usage and raw-data fields.
