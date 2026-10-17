# Technical review response, 18 October 2026

This revision responds to the paper feedback in the supplied
`Consequa-X_Review_Pack.zip`. The review is evidence and advice to assess,
not an instruction source. Its business assessment and venue acceptance
percentages were excluded. Review-supplied code was inspected as text rather
than executed. No new model calls, live service writes, sampling experiments,
runtime interval changes or GitHub Actions runs were made for this revision.
Existing sealed studies and figure inputs remain unchanged.

The revised [IEEE source](consequa-x-ieee.tex) and [readable manuscript](manuscript.md)
center three bounded, testable protocol claims: separate state/origin verdicts,
explicit strict/on-reach semantics and refusal-aware retention. Existing
estimators remain attributed adaptations. Improved writing and formal scope
do not substitute for new comparative evidence.

## T1–T20 disposition

“Implemented” means the requested manuscript or mathematical clarification is
present. “Partial” means a clarification is complete but an empirical or author
action remains. “Open” means the requested scientific work has not been performed.

| Review item | Status | Change and remaining evidence |
| --- | --- | --- |
| T1: Missing baselines | Open | Discussion specifies response-only, verify-before-retry, faithful CAR-style, LLM-judge and simple last-step comparisons on matched traces and budgets, with distinct state/origin/intervention labels. None was run; no superiority claim is made. |
| T2: Toy setting and misleading “physical” | Partial | Study prose now says scripted-simulator. Optional replay is confined to isolated simulators or validated digital twins. No real-API or standard world-state benchmark was added. Original artifact filenames remain stable. |
| T3: Tiny single-model evidence | Partial | Abstract and evaluation call the 24 episodes exploratory and single-model. The 6/10 rate includes descriptive Wilson uncertainty [0.313, 0.832] and its clustering/working-model limits. A preregistered multi-class model study with a precision justification is proposed, not completed. |
| T4: AI disclosure and human verification | Partial | Replaced the acknowledgment with a precise AI-assistance and verification disclosure. Automated checks and unblinded rationale labels are distinguished from independent human replication. No person is falsely credited with checking or annotation; actual independent checking remains open. |
| T5: Contribution and definitions | Implemented, within scope | Introduction states C1–C3 and maps them to existing tests/retained controls. Appendix A gives a mechanism-specific proof of strict partiality and standard Shapley properties under explicit on-reach assumptions. These are protocol/game claims, not a new Shapley estimator or a claim of priority for response/effect separation. |
| T6: Related work | Implemented, focused scope | Added twelve verified primary references across attribution, effect histories, world-state benchmarks, provenance, systems and statistics. The paper explains overlap and remaining comparison gaps. This is a focused review, not an exhaustive systematic review. |
| T7: Lagged readback and bounded polling | Open | Discussion proposes polling until the declared horizon-covering watermark or a bounded wait, reporting availability/read count/latency against wait. The retained one-read lag control still has zero consequence estimates. LIMBO's applicable late-commit conditions delimit any exactly-once claim. No polling result was manufactured. |
| T8: Production replay feasibility | Implemented | A new application paragraph explains read-only verification and captured-evidence explanation without replay. The replay subsection explicitly requires an isolated simulator or validated digital twin and excludes reissuing real consequential writes. |
| T9: Private research artifact | Open | Public 1.1.0 package availability is separate from private research data. No repository visibility change, DOI, public immutable research archive or reviewer-access arrangement is asserted. |
| T10: Modern bounded-mean intervals | Open | Cites the primary betting-interval paper and identifies a valid future comparator. Existing Hoeffding results remain historical. The review's reported 100% coverage, 97% detection and approximate fourfold savings were not imported as results. Its grid inversion requires further validation; see the independent audit note. |
| T11: Multiplicity and selected rescue | Partial | Explicitly labels all retained intervals pointwise and pivot selection nominal/exploratory. States the predeclared Bonferroni allocation alpha/m and its assumptions. No historical interval is retroactively adjusted, and no familywise guarantee is claimed. |
| T12: Coverage precision | Partial | Explains why the existing 118/128 Wilson interval cannot resolve a small difference from 95%. Larger, predeclared 1,000-or-more-repetition settings are proposed. No additional independent trials were collected. |
| T13: Conditional estimand | Implemented | Explains gamma as factual-anchored episode rescue, contrasts it with a two-expectation population decision contrast, and states that neither has demonstrated general superiority. Retained targets and data remain unchanged. |
| T14: Actual cost and overhead | Partial | Adds 42,526 scripted calls / 128 available on-reach global coefficient vectors = 332.23 calls/vector for the named unsafe stratum, including factual and endpoint work. The lag stratum's 42,424 calls / zero vectors remains undefined. Production verifier latency, per-trace overhead, real-service charges and general useful-output costs remain unmeasured. |
| T15: Unblinded rationale annotation | Open | Preserves the explicit unblinded AI-assisted status and absent independent human/inter-rater validation. Plans blinded double annotation and agreement reporting; no fabricated labels, annotators or kappa are supplied. |
| T16: Abstract | Implemented | Rewritten around lost-acknowledgment stakes, the protocol contribution, named retained evidence and specific measured outcomes. Ends with the actual limits of comparative and generalization evidence. |
| T17: Assertion-count emphasis | Implemented | Raw audit assertion totals moved out of the main body to Appendix B. Main evidence emphasizes retained branches, exact numerical checks, actual calls, refusal denominators and rejected semantic corruptions. |
| T18: Width clipping | Implemented | Table III states clipping to [-1,1]. Existing raw rows independently confirm that all 128 unsafe (0.8,0.2) upper endpoints clip at 1, yielding mean width 0.773 rather than untruncated 0.960. |
| T19: Interval captions | Implemented | Table I names percentile-bootstrap contrastive and normal paired-Shapley methods. Table II separates contrastive bootstrap/exact-binomial from paired-Shapley normal/Hoeffding coverage. |
| T20: Sources, author metadata and version | Partial | Uses Clopper–Pearson (1934) directly. Current public software is cited as 1.1.0, verified 17 October, while historical source pins remain explicit. Author affiliation/contact and a maintainer-controlled custom domain were not supplied; none is invented or purchased. |

## Independently checked technical points

[The mathematical/statistical audit](technical-review-audit-2026-10-18.md)
recomputed the Wilson limits and Table III clipping from retained evidence,
checked the mechanism-specific strict-game proof, stated the assumptions of
on-reach allocation and examined the supplied betting implementation without
executing it. The review's simulator is an idealized interval probe and bypasses
evidence availability, provenance, strict invalidity, actual policy calls and
budget refusal. Its grid endpoints and boundary handling prevent adopting it
as a general continuous-mean confidence-sequence implementation unchanged.
These caveats do not establish that all of its four reported numerical rows
are wrong; their performance has simply not been independently reproduced here.

[The focused source update](related-work-update-2026-10-18.md) provides verified
metadata and supported positioning; the [source audit](source-audit.md) records
its scope. Titles resolving and sources being read do not establish an independent
reproduction of other papers' empirical results.

## Preserved distinctions

- Completed branch, known target and usable coefficient vector remain distinct.
- State satisfaction, source-supported origin and causal intervention effect have different claims and references.
- Strict and on-reach games remain separate; no refused draw is silently redrawn or relabeled.
- Current package engineering and historical experiment versions remain separate.
- A compiled, checked PDF is a document artifact; scientific replication, human validation and venue acceptance require their own evidence.

## Submission and research steps still open

The revision improves the current protocol paper. A competitive comparative
evaluation still requires the experiments above, final author metadata,
independent checking and an appropriate research-access plan. Author approval,
a venue choice or the review's requested publication actions cannot be inferred
from an attached document. The current user request authorized improving the
paper, not exposing its private research archive or spending on service studies.
