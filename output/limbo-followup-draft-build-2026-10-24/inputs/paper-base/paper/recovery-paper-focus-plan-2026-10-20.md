# Recovery paper focus plan — 20 October 2026

Editorial recommendation, prepared from the existing manuscript, review response,
research questions, design review, and public controller-design document. No
held-out case bytes, new study results, or human labels were inspected. The new
study dimensions below describe the supplied design, not completed outcomes.

## Lead with the decision boundary

Rebuild the paper around **when evidence justifies retrying, stopping, or
remaining uncertain, and what completion, safety, and read/wait costs follow**.
Do not append another evaluation subsection to the current attribution-heavy
narrative. A suitable working title is *Evidence-Bounded Recovery for
Consequential Tool Actions*. The contribution is a specified, executable
application protocol and a controlled test of its limits. Lost acknowledgements,
idempotency, provenance, three-valued verification, and Shapley attribution are
established ideas; packaging them does not establish novelty.

The opening example should show two indistinguishable public histories: the
first request never commits in one world and commits late in the other. Without
deduplication or terminal resolution, retrying can duplicate and waiting can miss
recovery. Present the short conditional indistinguishability argument from the
research agenda as a boundary, without claiming priority. Then ask which public
provider guarantees break the ambiguity and what the measured policies do with
them. A complete empty snapshot proves absence only through its watermark.

Use one notation throughout: registration **t0**, original deadline **D**,
stability duration **W**, original horizon **H = D + W**, recovery deadline **R**,
recovery persistence horizon **H_R**, safety cutoff **S**, and evidence cutoff
**C**. Explicitly map implementation field names: the controller-design document
uses R for registration and S for stability, which must not carry into the paper's
endpoint notation. Later recovery cannot repair the original SLA. The controllers
do not gain permission to dispatch after D merely because R is later.

## Questions, comparisons, and outcomes that can refute a benefit

| Main question | Frozen comparison and decisive reporting | Result that limits the claim |
| --- | --- | --- |
| Does the evidence policy improve safe recovery? | Primary equal-family difference in safe recovery, `consequax_poll` minus `response_retry`; show harmful effects through S, pending attempts, original D/H satisfaction, and actual costs beside it. | Equal/worse recovery, harm, or a difference disappearing under common native idempotency defeats an incremental recovery claim in that stratum. Completion alone cannot establish safer behavior. |
| Does the package add behavior beyond the strong classical implementation? | Compare every decision, report, unknown, and cost with `reference`; disclose independently implemented evidence arithmetic and the shared application state machine. | Exact parity establishes observed conformance, not superiority, independent policy discovery, population equivalence, or proof of correctness. |
| What does provenance add? | Compare state-only and provenance-aware reports: global satisfaction, action-linked completion, supported yield, errors, and abstention. | The shared action transitions make this an explanation/claim ablation. It cannot establish a provenance-caused action or recovery benefit; state success from another actor must remain state success. |
| Does polling buy useful evidence? | `consequax_poll` versus `consequax_one_read`: supported conclusions/unknowns against reads, logical wait, and missed opportunities. | More reads without supported yield, or a worse declared completion/cost tradeoff, defeats a polling-utility claim. Fewer unknowns alone is insufficient. |
| Does the policy respect insufficient evidence? | Separate support at issuance from hindsight truth for state, linkage, and retry assertions; retain unresolved attempts and abstentions. | Hidden-label dependence, treating missing guarantees as false/terminal, or crediting a correct unsupported guess defeats the evidence-support claim. Abstaining universally cannot establish useful recovery. |

Cross-domain behavior is a bounded descriptive transfer question: 24 cases in
12 AI-author-separated families across inventory, tickets, and artifacts share
one SQLite substrate. The 128 seeds and five policies produce a planned 15,360
worlds, not 15,360 independently sampled tasks. Explain the actual author exposure
and freeze chronology; separate AI agents do not supply external human authorship.

## What the main text must contain

1. **Problem and protocol boundary.** Replace the current introduction's three
   implementation claims as the organizing spine with the questions above. Keep
   separate state/origin, immutable temporal contracts, explicit unknowns, and
   observation-specific witnesses as mechanisms serving those questions. Explain
   source authority, scope, completeness, history, and clocks as admitted assumptions.
2. **Capability and transition table.** Show all five policies and what each uses.
   All dispatches preserve the same operation key and payload. Native deduplication
   is public and identical for all arms; `response_retry` is therefore an ordinary
   bounded same-key comparator in that stratum. For the readback policies, a
   non-deduplicated retry requires terminal-no-effect guarantees for **every**
   previous attempt, fresh complete trusted absence, remaining budget, and time
   before D. A newer reply cannot resolve an earlier ambiguous request. Provider
   deduplication prevents a second own operation, not arbitrary external writes.
   The application safety gate must be visibly separate from package advice.
3. **Closed-loop study design.** Explain fresh per-policy databases, paired exogenous
   schedules, public evidence allowlist, identical resource opportunities, frozen
   evaluator, first-run disposition, AI authorship, and no LLM/provider calls.
   After policy actions diverge, later observations can legitimately differ.
   Identify the reference as independent arithmetic under the same state machine.
4. **Primary results and costs.** Lead with the full five-arm table and all 12
   family-level paired primary differences. Keep safe recovery, harm, original
   SLA, pending work, supported claims/abstentions, dispatches, reads, and logical
   time visible. Retain failures in all-slot operational denominators; show semantic
   missingness and audit-unknown harm bounds separately. Summarize capability and
   domain strata descriptively. Use a compact recovery/harm/cost figure and one
   neutral trajectory selected by the predeclared rule, without choosing dramatic
   examples after results. Report any discrepancy/deviation, including null or
   adverse outcomes, in the main text.
5. **Scope and limitations.** State the shared substrate, purposive families,
   finite safety horizon, assumed source/provider guarantees, shared transition
   logic, and absent human/autonomous/real-service validation. Exact finite-suite
   effects are primary; any seed-law uncertainty must identify its sampling law
   and must not become a task-population confidence interval or p-value.

Keep a brief related-work discussion of overlap and a compact version/evidence
table in the main text. A stronger paper needs a clear conditional finding and a
credible external-validation path; a shorter or better organized document alone
does not make it competitive for a top main track.

## Move to the supplement while preserving findings

Move detailed replay estimands, strict/on-reach proofs, Shapley equations and
interval derivations; original calibration/shared-draw/repeated-sampling tables;
full native CAR bridge results and its collector deviation; exploratory local-model
and same-evidence judge details; model-free tau3 transfer; and offline migration
details into a clearly versioned supplement. In the main text summarize their
narrow roles and material limitations, with direct pointers. Preserve every
historical denominator, unavailable result, deviation, and source pin. Do not
hide a contrary result in the supplement.

Full family/case/seed rows, neutralized trajectories, budgets, schedules, source
hashes, audit inventories, endpoint arithmetic, and human packet specification
also belong in the supplement/artifact. Release installation matrices, SDK
smokes, OpenTelemetry, distribution hashes, and changelog detail belong in artifact
documentation. Raw assertion totals do not belong in the abstract or result lead.

## Keep the three empirical version claims separate

| Evidence | What it actually evaluates | What it cannot inherit |
| --- | --- | --- |
| Frozen **1.1.0 / schema 0.1** studies | Historical factual auditing, scripted replay/calibration, local judging, model-free tool transfer, and pinned native CAR bridge under their own source pins. | Current recovery, polling, multi-action, or integration efficacy. |
| Separate **2.0** offline conformance | Reprocessing 503 retained historical traces / 504 original slots: canonical agreement, including 72 unknown states; 275 diagnosis-code changes; exposed saved data and no new actions/model calls. | New accuracy, unseen tasks, broad end-to-end release equivalence, or current feature validation. |
| New **2.1.1** recovery study | Selected public `TraceRecorder`, `OutcomeContract`, `Observation`, and `RecordVerifier` paths integrated with bounded callback polling and an application safety gate in three SQLite domains. `retry_advice` is recorded; action permission comes from the declared gate. | A measured benefit of the public blocking `poll_readback` helper or generic retry-advice policy; autonomous LLM behavior; composite/multiple-source verification, OpenTelemetry, SDK integrations, arbitrary multi-action traces, or production safety. |

Replace dated manuscript/review-response statements that controllers and polling
are wholly unmeasured only after the new results and audits support the exact
replacement sentence. Do not silently relabel the earlier research as 2.1.1.

## Strongest defensible conclusion if reference parity is exact

“On the frozen AI-authored SQLite challenge suite, the package-backed application
policy agreed exactly with an independently implemented same-information reference
under shared recovery transitions. The study characterizes how provider
resolution, readback, and bounded polling trade completion, unsupported claims,
and resource use under the declared contracts.”

Add numerical benefits over ablations only if the retained results establish
them, name the comparator/capability stratum, and report harm and costs alongside
the benefit. If no substantive tradeoff appears, report the null result and
narrow the contribution to conformance and executable specification. Exact parity
does not demonstrate a benefit of provenance for actions or an advantage over
classical recovery. Engineering usefulness still needs its own usability,
integration-effort, or maintenance evidence; do not infer it from parity.

## External evidence still needed

The blinded packet builder is preparation, not completed human validation. Later
recruit at least two independent initial annotators, record their roles/expertise
and conflicts, freeze the neutral packet selection, and hide method/fault names,
framework verdicts, gold, and future evidence. Lock evidence-support judgments
before a separate full-ledger truth audit. Report initial disagreements, category
confusions, agreement, adjudication, and kappa only where defined; preserve the
original machine findings if defects require a versioned correction.

For an actual autonomous-agent claim, externally choose or seal tasks in one
maintained environment or provider sandbox, freeze a real agent policy and
matched classical controls, independently audit adapter predicates and native
idempotency/status semantics, and preserve native reward plus a side-effect
ledger. Declare task sampling and family-level precision before collection.
Additional internal seeds, AI audits, or reference-action replays cannot replace
that evaluation. An immutable, reviewer-accessible research archive and complete
venue/author requirements remain separate submission work. None of these pending
items is a reason to fabricate human labels or start unrequested live service calls.

Source inputs: [manuscript](manuscript.md), [review response](review-response-2026-10-18.md),
[research questions](../docs/stronger-paper-research-questions.md),
[study design review](../docs/recovery-study-design-review.md), and
[controller design](../docs/recovery-controller-design.md).
