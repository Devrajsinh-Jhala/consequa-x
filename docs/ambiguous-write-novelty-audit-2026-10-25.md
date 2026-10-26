# Ambiguous-write recovery: novelty audit and prospective specialization

25 October 2026. This is a design and primary-literature audit, not a claim of
implemented novelty, collected evidence, or conference readiness. No model
requests, benchmark episodes, workflow executions, human review, or manuscript
changes were performed for this audit. Existing frozen experiments remain
unchanged. GitHub Actions must remain disabled.

## What the current study establishes

`research/limbo_agent/policy.py` deliberately wraps the unchanged native
`OutcomeGuard` in ConseqaX receipts. Its source states that this is a
representation/integration comparison. The manuscript correctly preserves that
scope. Receipt integration cannot be relabeled as a new recovery algorithm.

The local upstream source inspected for this audit is
`C:/Code/ConsequaX-Research/limbo-pinned-2db09fba/limbo/policies.py`, pinned by the
existing study to `2db09fba22a0572a70639162a808906409f612a8`. Three concrete
behaviors motivate a different operational policy:

1. `_find_pending` normally excludes an intent after its state becomes `found`.
   A verified ambiguous write is consequently suppressed once; a later identical
   proposal can cease to match that entry. This is documented native behavior,
   not an implementation defect to silently fix in a comparator.
2. `_after` records ambiguous errors, but does not register every successful ACK
   as an enduring completed or unresolved operation. A new registry can retain
   every admitted logical operation and all attempts, rather than only the
   currently ambiguous error queue.
3. An `absent` read after a visibility wait can supersede pending work. Visibility
   lag bounds when committed work can be read; it does not bound when an
   in-flight request can still commit. The proposed policy must preserve that
   distinction even if it lowers completion under a weak contract.

The earlier project recovery controller already implements an all-attempt
terminal gate, stable operation keys and an admitted native-idempotency
exception (`docs/recovery-controller-design.md`). Those rules are prior project
work, not new discoveries in the next experiment.

## Primary literature and exact overlap

All links below were checked against primary author papers or the author
repository on 25 October 2026. Submission dates identify versions; they do not
imply peer review or acceptance. Repository statements are scoped to the
inspected public documentation. Pin exact source bytes before executing any
external-code comparator.

| Primary source | Identifier / date | Established overlap and implication |
| --- | --- | --- |
| [Verified Tool Calls Improve LLM Agent Reliability Under Non-Atomic Failures](https://arxiv.org/abs/2608.02645) | arXiv:2608.02645v1; submitted 31 July 2026 | Postcondition checks, verify-before-retry and idempotency keys are already proposed. These are baseline mechanisms, not a new contribution. |
| [Where Does Exactly-Once Live?](https://arxiv.org/abs/2609.29095) | arXiv:2609.29095v1; submitted 24 September 2026 | LIMBO supplies the external environment, contract-aware guard and observation-equivalence/late-commit impossibility argument. Its documented propositions must be credited; waiting out read lag is not a solution to unbounded in-flight time. |
| [RetryBench](https://arxiv.org/abs/2610.15884) | arXiv:2610.15884v1; submitted 11 October 2026 | Separates unsupported retry permission from realized recovery and compares changed/valid operation keys using compatible-world replay. Permission scoring and shared-response worlds are established measurement ideas. |
| [OpenOnce author repository](https://github.com/memovai/openonce) | Software; README inspected 25 October 2026 | Durable per-intent receipts, `UNKNOWN` lifecycle, provider capabilities, reconciliation, grace windows and probe conformance are implemented concepts. A persistent registry plus capability checks is insufficient on its own to establish novelty. |
| [Beyond Single-Use Tokens: Durable Authorization State for Replay-Resistant LLM Agent Actions](https://arxiv.org/abs/2608.01710) | arXiv:2608.01710v1; submitted 3 August 2026 | CapLease studies durable canonical authorization state, transactional Issue–Prepare–Commit and a matched Server Ledger. Durable replay control is established; a local ledger does not manufacture an idempotent external sink. |
| [When May an Agent Stop?](https://arxiv.org/abs/2608.23623) | arXiv:2608.23623v1; submitted 22 August 2026 | Evidence-Carrying Termination binds completion claims to typed trace evidence and deterministic replay. Merely attaching evidence to `COMPLETE` is not new. |
| [Controller-Agnostic Runtime Safety Certificates for Tool-Using AI Agents via Data-Driven Robust Reachability](https://arxiv.org/abs/2610.16865) | arXiv:2610.16865v1; submitted 12 October 2026 | Runtime shielding with controller-independent risk certificates is established. Our proposed method is an explicit operational-contract specialization, not the first agent safety shield. |
| [Proof-Carrying Contracts: Commitments AI Agents Cannot Break](https://arxiv.org/abs/2610.28484) | arXiv:2610.28484v1; submitted 20 October 2026 | PC2 checks machine-verifiable per-call obligations over model-admitted outcomes. Generic proof-carrying action admission and capability modules are not available as priority claims. |
| [Certified Execution Harness for Agentic AI](https://arxiv.org/abs/2610.31376) | arXiv:2610.31376v1; submitted 22 October 2026 | Petri-net supervision and least-intrusive execution control already address permitted actions and replanning costs. Do not claim generic maximally permissive control as invented here. |
| [Loud Failures, Quiet Failures](https://arxiv.org/abs/2610.10062) | arXiv:2610.10062v1; submitted 7 October 2026 | Separates detection, plan change and recovery across six model configurations and 24 tasks. A multi-model fault benchmark alone is insufficient novelty; measure distinct operational mechanisms and repeated clean-run variability. |

This audit supports a narrow candidate contribution, not a defensible claim that
the surrounding architectural ideas are absent from all literature. The next
paper should distinguish its executable specialization and evidence from the
broader mechanisms above, with adverse comparisons preserved.

## Proposed contribution: finite public-evidence obligations

Implement an explicit finite-state specialization for ambiguous writes, outside
the frozen historical source. For each trusted logical operation, maintain the
set of public-observation-compatible execution states and the obligations still
needed to admit its next dispatch. Produce either a small independently
checkable admission certificate or a compatible delayed-commit counterexample.

The candidate contribution is the combination of an operationally explicit
decision procedure, component-wise attempt accounting, counterexample-bearing
refusals and measured safety/utility/cost boundaries. It is not a new delivery
guarantee, generic proof architecture, or assertion of first use.

### Public inputs and state

The caller supplies a stable operation identity, effect-relevant canonical
payload and admitted provider/source capability declaration. A model tool-call
ID is not logical operation identity. Without a trusted equivalence rule,
different payloads must not silently collapse into the same semantic intent.
An explicitly new authorized operation may legitimately repeat the same payload.

Retain every actual attempt, including ACKs, timeouts, explicit failures,
key/payload identity, dispatch time, affected components and attempt-scoped
terminal-nonexecution evidence. Retain successful or observed-complete operation
entries for the entire declared operation scope. One resolved attempt never
resolves an older ambiguous attempt.

The policy sees only public responses, admitted source evidence, clock values,
metadata and its own registry. No task targets, fault assignments, pending-event
queues, actual effect ledger, oracle verifier, grades or evaluator truth enter
the decision procedure. Scope/source/clock completeness is checked before an
observation affects admission.

### Admission branches and certificates

For a repeated overlapping write, permit only a branch whose explicit premises
hold:

1. **Protected replay:** the exact original logical operation key and canonical
   payload remain covered by an admitted atomic deduplication guarantee,
   including pending work and the relevant retention window. A keyed batch may
   resume only if its contract actually supplies identical-payload resume
   semantics. A changed key, expired protection or changed payload fails this
   branch.
2. **Declared natural effect idempotency:** the admitted operation contract
   makes repetition harmless for the specified effect predicate. This branch
   must distinguish repeated executions from repeated external effects; it
   does not prove physical once-only execution or arbitrary collateral safety.
3. **Resolved absence:** every earlier attempt that could affect a proposed
   component has an admitted terminal-nonexecution guarantee, or a documented
   in-flight bound has actually elapsed; an admitted fresh exhaustive read
   establishes the required absence. A read watermark alone does not certify
   terminality. Global exact-count targets can also be affected by other actors,
   so this branch is only as strong as the declared race/scope assumptions.

Every actual repeated dispatch records a certificate binding the operation,
canonical payload, all prior overlapping attempt identities, capability version,
evidence identities/hashes, decision time, branch and evaluated premises. An
independent standard-library checker rederives premises from saved public
inputs. Hash binding checks integrity of recorded bytes; it is not provider
authentication. A receipt that merely asserts `safe=true` is insufficient.

For a resolved operation, suppress a repeated proposal with a distinct
policy-result annotation, never a fabricated native service return or invented
fresh verification. Record whether the conclusion is acknowledged, observed
current state, attributed outcome or temporally settled state.

### Refusal and counterexample

If an earlier overlapping attempt can still commit, retain it as possible.
Refuse an unprotected additional write. Emit a symbolic compatible schedule
showing the earlier attempt committing after the negative snapshot and after
the proposed repeat, with both effects counted. The schedule uses the public
contract and transcript only; it never reads the actual hidden event queue.

The independent checker verifies compatibility with every admitted observation,
time bound, terminal guarantee and key guarantee, then verifies the relevant
duplicate predicate. A counterexample is a witness that a retry lacks support,
not a prediction that this episode's hidden world will realize that schedule.
Where the declared model cannot construct a concrete witness, report refusal
with unresolved obligations instead of inventing a witness or a theorem.

### Partial batches

Keep original and recovery component sets separate. A visible missing row is
not retry authority if any overlapping original attempt can still supply it.
An unkeyed recovery subset is permitted only after every earlier overlapping
attempt for each component is terminal and its absence is admissible. Never
clear original obligations when a subset is reissued. Preserve component/key
relations and forbid changed-payload reuse under an original batch key.

If the source cannot expose complete component history or a partial-batch
termination guarantee, remain unresolved. Do not infer these capabilities from
the existence of a `missing_rows` field.

### Evidence scheduling

Start with a deterministic documented eligibility rule, not an unvalidated
claim of optimal active learning. Read opportunities and all budgets match the
strong comparator. Avoid retry-licensing reads before the declared visibility
and in-flight premises could jointly hold; allow separate positive-evidence
reads only if their cost/latency purpose is declared. With an unbounded
in-flight delay and no valid deduplication, a negative read can never license a
retry, however long the controller waits.

A subsequent finite minimax query planner is optional research, not part of the
initial novelty claim. Any optimality claim requires a precise finite world
model, objective, executable exhaustive reference and explicit state-size bound.

## Matched comparisons and ablations

The primary live comparisons should include unchanged native `guard`, its
existing ConseqaX receipt adapter, and the new obligation policy. Preserve
`vanilla` and `sdk_retry3` as recognizable safety/utility anchors where resource
cost permits. Native guard is an honest supplied heuristic comparator, not an
optimal admissibility oracle.

Add an equally informed conservative reference with persistent identity,
all-attempt terminality and the same capabilities. Agreement in permission is
expected. If this reference matches all benefits, attribute results to those
established rules rather than the certificate representation. Where an executable
OpenOnce comparator is feasible under the exact same capability contract,
include it or state precisely why its service/reconciliation interface differs;
do not pass it extra terminal information.

Use the following mechanism ablations, labeled as intentionally weakened
research conditions and run only in simulation:

- Forget verified/ACKed intents after one suppression, retaining everything else.
- Replace all-attempt terminality with latest-attempt terminality.
- Interpret complete visible absence as terminal nonexecution.
- Collapse the original batch and recovery subset into one pending record.
- Use fixed periodic queries instead of the declared eligibility schedule.
- Keep the same decisions but remove certificates, to isolate their logging
  and independent-checking cost rather than fabricate decision superiority.

Use a full-information offline oracle only as a labeled evaluator reference.
It is not a deployable baseline and may not feed public-controller decisions.

## Proof obligations, adversarial tests and falsifiers

Before measurement, independently enumerate small synthetic histories (for
example up to three attempts, three batch components and bounded discrete
event times) and compare the policy with a separately implemented exhaustive
compatible-world admission reference. Synthetic tests are not additional
independent real-world tasks.

Required adversarial histories include:

- An older attempt remains pending while the most recent attempt reports
  terminal failure; repeat remains unprotected.
- ACK followed by repeated identical proposals, including three or more later
  proposals; ACK never becomes proof of current effect state or erases identity.
- A verified-found intent proposed repeatedly after its first suppression.
- An empty exhaustive read followed by a late commit; visibility SLA elapsed,
  but no in-flight bound exists.
- Partial original batch, recovery subset, then late original completion;
  changed batch payload under the same key must fail protected replay.
- Changed/omitted/expired key; parameter mismatch; key retention ends before
  the attempted repeat; valid pending-work coalescence as a positive control.
- Source/scope/watermark mismatch, incomplete history, unavailable source,
  malformed certificate and missing prior attempt identity.
- Another actor produces a matching record without origin evidence; distinguish
  global target state from this operation's contribution.
- First-delivery duplication, dishonest capability metadata and behavior beyond
  admitted bounds, explicitly illustrating guarantee failure boundaries.

Falsify permission soundness if any admitted repeat has a compatible continuation
that violates the declared additional-effect budget. Falsify counterexample
validity if a witness contradicts any public input. Falsify relative maximality
if the exhaustive reference permits an action the policy refuses under the
same finite model. Do not claim maximality until that property is checked.

## Prospective hypotheses and reporting

H1: The obligation policy reduces unsupported repeat admission versus native
guard in late-commit and repeated-proposal conditions. This is permission
soundness, distinct from the realized duplicate outcome.

H2: Persistent all-attempt and component-wise state explains improvements;
its removal worsens those endpoints. A null effect defeats that mechanism
explanation and must remain visible.

H3: The policy preserves protected-replay progress under admitted atomic key
contracts but abstains more under unbounded keyless ambiguity. Zero duplicates
with universal refusal is not a useful success result.

H4: Eligibility scheduling reduces actual reads at a matched ceiling without
an undisclosed increase in unsafe admissions; completion/latency tradeoffs are
reported, not assumed absent.

Freeze source, all task/model selections, fault and budget schedules, analysis
and stopping rules before new measured runs. Use fresh base-instance parameters
outside inspected development and historical runs. Report model-family results,
task/template clusters, clean repeated-run variation, normal return/grade
availability, unsupported admission, realized duplicate executions and effects,
omissions, supported completion, unresolved outcomes and actual work costs.
Count unique tasks and independent clusters explicitly; extra seeds, faults,
models and arms do not magically create independent task families.

No model label is a human validation substitute. Automated objective ledgers,
independent code paths and counterexample checks can support their own stated
claims without human participants. They do not establish independent external
replication, authentic provider guarantees, universal exactly-once effects or
acceptance at a particular conference.
