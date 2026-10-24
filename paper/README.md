# ConseqaX research paper

[conseqax-research.tex](conseqax-research.tex) is the current primary generic IEEE
manuscript; [conseqax-research.md](conseqax-research.md) is its readable companion.
It centers an evidence protocol and a controlled software/systems evaluation of
ambiguous-action recovery. The author is Devrajsinh Jhala, **Independent
Researcher**. No specific conference or journal has been selected, and a contact
email has not been supplied.

The [reviewed 16-page PDF](../output/pdf/limbo-audited-paper-2026-10-24-v4/ConseqaX_Research_Paper.pdf)
contains the completed controlled studies and audited native comparison.
The [completion receipt](../output/limbo-paper-completion-2026-10-24/completion-receipt.json)
binds the exact sources, both cohorts, passed audits and all-page visual review.
Its source/figure copies and diagnostics accompany the immutable PDF bundle.
Generic IEEE formatting is complete; a specific venue's length, anonymity,
author/contact and submission requirements remain separate.
The [earlier 12-page development build](../output/pdf/native-integration-2026-10-22/ConseqaX_Research_Paper.pdf)
and earlier dated artifacts remain historical records.

## Current controlled evaluation

Study A uses the pinned **2.1.1** package in local SQLite applications. Its
[prospective protocol](../output/recovery-controller-protocol-2026-10-20/protocol.json)
binds source `22e88498cff0e2afd1549803fb4d9645902e74b9` and the complete schedule:
24 authored cases, 12 purposive families, 128 seeds, and five deterministic
policies, producing 15,360 retained worlds with zero execution failures. None of
the recorded endpoint or resource metrics varied across seeds within a
case-policy group; these are not 15,360 independent tasks.

The [audited findings](recovery-study-findings-2026-10-20.md),
[TeX results input](recovery-study-results.tex),
[original-host audit](../output/recovery-controller-audit-2026-10-20/audit-receipt.json),
and [portable artifact audit](../output/recovery-portable-audit-2026-10-20/portable-audit-receipt.json)
retain the exact counts and limitations. Every readback policy achieved
1,792/3,072 operational safe recoveries, versus 1,024/3,072 for the declared
response-driven retry rule. The strong reference matched the package; polling
added reads without an outcome benefit over one final read under Study A's
schedules. These findings establish conditional behavior and observed
conformance, not superiority over an equally informed reference or general
production safety.

The [postcollection packaging deviation](../output/recovery-artifact-finalization-2026-10-20/finalization-record.json)
is part of the result: all worlds and the summary were retained, but the
original terminal manifest and receipt were absent. A separate finalizer
preserved the retained bytes and created those packaging files without rerunning
worlds; the original exit status and termination cause remain unknown. Artifact
audits do not establish source authenticity or absence of off-record execution.

The separately frozen **Study B availability follow-up** completed all 960 worlds
with zero failures: 64 controlled profiles across three domains and five policies.
The run closed normally with a retained
[terminal receipt](../output/recovery-availability-study-2026-10-20/completion-receipt.json),
and the [audit](../output/recovery-availability-audit-2026-10-20/audit-receipt.json)
checked all 1,925 artifacts and 960 SQLite snapshots, including recorded-host byte
checks. The [registered protocol](../output/recovery-availability-protocol-2026-10-20/protocol.json)
and [coverage analysis](../output/recovery-availability-audit-2026-10-20/coverage-analysis.json)
retain every profile and outcome. This controlled follow-up was designed after
Study A and is not an independently sampled task benchmark.

All methods achieved 192/192 safe recoveries, one effect per world and no own
duplicate/unwanted events; physical histories agree in every five-arm cell.
One final read yielded 3/192 correct state/linkage reports, with 189 unknown,
192 reads and mean logical time 150 ms. Polling/reference yielded 81/192, with
111 unknown, 741 reads and mean 224.375 ms. State-only had the same state yield
and resources but abstained on all 192 linked reports. Response retry reported
192/192 correctly from ACK, using no reads and mean 2 ms; this uniformly safe
design cannot estimate its false-success risk. The polling state-yield gain of
78/192 = 26/64 profiles is shared by the classical reference and state-only rule;
there is no physical recovery gain or strong-reference superiority. These are
finite-grid descriptions and simulated logical times, not task-population
inference or production latency.

The current paper uses SQLite/effect-ledger ground truth, separately implemented
reference rules, automated artifact audits, and controlled comparisons. It makes
no interpretability, preference, or rationale-quality claim and has no planned
participant study. The historical unblinded T15 rationale claim is excluded.
The [20 October review addendum](recovery-review-response-2026-10-20.md) records the
scope change and remaining objective validation gaps. No human-review packet is
part of the current paper.

## Completed native LIMBO comparison

The separately [published follow-up protocol](../output/limbo-followup-protocol-2026-10-24/protocol.json)
completed all 96 planned slots on 24 conditions from 12 base instances. All 96
native grades passed [independent replay](../output/limbo-followup-audit-2026-10-24/audit-result.json)
and the [portable comparison](../output/limbo-followup-portable-audit-2026-10-24-v2/audit-result.json)
agreed. Normal returns and semantic success remain separate: three native error
returns retain audited post-settlement grades.

| Arm | Graded | TS true | Native EOS true | Normal returns |
| --- | ---: | ---: | ---: | ---: |
| Vanilla | 24/24 | 21/24 | 16/24 | 24/24 |
| SDK retry | 24/24 | 24/24 | 14/24 | 24/24 |
| Native guard | 24/24 | 21/24 | 16/24 | 23/24 |
| ConseqaX guard | 24/24 | 20/24 | 15/24 | 22/24 |

The SDK integration emitted three audited receipts in three measured episodes.
It preserves the supplied strong guard's control law; these findings do not
establish a new recovery algorithm or superiority. Native EOS has domain-specific
accounting and is not a universal exactly-once guarantee. The
[analysis and actual figures](../output/limbo-followup-analysis-2026-10-24/results.md)
retain all matched contrasts, condition strata, adverse effects, costs and unknown usage.

The original interrupted 96-slot condition remains separate: six replayed grades,
one interrupted trajectory and 89 unstarted slots, with 90 grades unavailable.
Its [later preservation archive](../output/limbo-official-interruption-2026-10-24/manifest.json)
is not an original collector seal. The follow-up was declared after partial-data
exposure, reuses the same 12 base instances and changed the execution environment;
it is neither an unseen holdout nor an independently sampled replication.
The two denominators are never pooled into 192 independent tasks.

## Historical airline development: no official matrix collected

The [automated workflow](../docs/native-external-benchmark.md) implements four
matched native airline conditions on twelve prespecified task IDs (48 planned
slots), local inference, required native DB/communication grading, complete
request/tool capture and offline replay. Its 190 benchmark-infrastructure tests
passed before collection; a further 20 cover the auxiliary resource observer
and 18 cover the one-shot pipeline.

The first unmodified development episode returned 14 model completions and
five actual tools. Its [independent saved-artifact audit](../output/native-development-2026-10-21/native-19-000-audit/audit-result.json)
passed; native task reward was **0**, and its empty communication requirement
passed vacuously. This establishes integration, not framework benefit. Later
development checks fix and retain hidden SDK retry and null-serialization
issues before any official collection. The exact-source native check returned
grading, but guarded readiness failed; there is no official pilot result.
GitHub Actions stays disabled, with no human review or paid inference.

The fresh final-source native check returned 12 completions and five tools.
Its [audit](../output/native-development-2026-10-21/native-19-002-audit/audit-result.json)
also passed, including exact native-request/HTTP/context linkage; native reward
remains zero. The first guarded check timed out without native grading. The
amended check also timed out: nine model invocations, eight completions and five
read-only native tools, with no native simulation, package receipt or guard block.
Its [partial failure-integrity audit](../output/native-development-2026-10-21/guarded-20-001-failure-audit-2026-10-22/audit-result.json)
verified the complete retained prefix and explicitly declined native-reward
validation. Returned token usage excludes the timed-out request's unknown usage.

The [terminal pipeline receipt](../output/native-finish-pipeline-2026-10-21/pipeline-receipt.json)
records refusal before readiness, protocol publication and official collection.
No official trajectory ran, and no automatic replacement is pending. Development
settlement is 44/64 excluded-task requests; 20 unused requests were released.
The [resource-observer finalization](../output/native-resource-observer-finalization-2026-10-22/README.md)
preserves its incomplete closing status and actually sampled coverage.

These excluded airline checks remain feasibility evidence. The later LIMBO
comparison above supplies the completed native fault comparison; it does not
manufacture an official airline score or replace a collected airline matrix.

## Product version and evidence boundaries

The retained 20 October product release is **2.1.2**, with a
[release record](../output/release-2.1.2-2026-10-20/README.md) and
[publication receipt](../output/release-2.1.2-2026-10-20/publication.json).
The controlled research retains its 2.1.1 pin. Publishing a newer package does
not rerun or relabel an experiment. The study exercises selected recording,
contract, observation, and record-verification paths plus explicit application
controller code; it does not validate every product feature or the public
blocking polling helper. Release/integration engineering remains separate from
scientific evaluation.

Earlier evidence retains its original versions and targets:

| Historical evidence | Retained scope |
| --- | --- |
| [Matched local factual study](matched-study-findings-2026-10-18.md), 1.1.0 | 503/504 episodes; three small local models; captured-evidence comparison, not independent task-population sampling. |
| [Same-evidence local judge](../output/matched-trace-judge-analysis-2026-10-18/analysis.md), 1.1.0 | 84 selected inputs; one small local judge, not a general ranking. |
| [Maintained task/tool state transfer](../output/tau3-state-transfer-audit-2026-10-18/final-audit.md), 1.1.0 | 656 deterministic retail/airline control cells; native DB matching, not autonomous benchmark reward. |
| [Native CAR comparison](../output/upstream-car-audit-2026-10-18/final-audit.md), 1.1.0 | 1,024 paired groups; 640 eligible point vectors agree and 384 remain unavailable; a disclosed collector limitation is retained. |
| [Offline migration conformance](../output/v2-migration-audit-2026-10-19/README.md), 2.0 | 503 retained traces / 504 original slots; exposed-data compatibility, not new accuracy. |

## Historical manuscript and compiled artifacts

[consequa-x-ieee.tex](consequa-x-ieee.tex) and [manuscript.md](manuscript.md) are
the historical extended manuscript, preserving detailed replay, calibration,
and earlier evidence treatment. They are not the current primary paper.

The [checked 19 October extended PDF](../output/pdf/external-validation-2026-10-19/Consequa-X_IEEE_Paper.pdf)
and its [quality receipt](../output/pdf/external-validation-2026-10-19/qa.json)
remain historical artifacts. That receipt binds the exact seventeen-page,
nine-figure source/PDF revision; it does not cover the new focused manuscript.
The focused manuscript has its own completed compilation and all-page review
linked above. Document quality does not establish scientific validity or
venue-specific submission compliance.

## Remaining research and submission work

The fixed matched native comparison, saved-effect replay, results integration
and generic IEEE manuscript are complete. Broader model/task sampling,
independently operated services, source authentication and external replication
remain limits rather than experiments claimed here. No population inference or
algorithmic-superiority claim is supported by this finite matrix.

An immutable evidence archive, final author/contact metadata, and an actual
venue's length, anonymity, disclosure, and submission requirements remain open.
The public repository is not an archival DOI. No conference acceptance or
submission is asserted. **GitHub Actions remains disabled.**

## Evidence navigation

- [Review addendum](recovery-review-response-2026-10-20.md) and [historical T1-T20 response](review-response-2026-10-18.md).
- [Evidence ledger](evidence-ledger.md): historical claim-to-artifact mappings; read its dated entries with the current scoped findings above.
- [Primary-source audit](source-audit.md), [related-work notes](related-work-update-2026-10-18.md), and [bibliography](references.bib).
- [Current figures](figures/recovery-method-overview.pdf) and [all-family contrasts](figures/recovery-family-primary-contrasts.pdf).
- [Native-agent validation preflight](../docs/native-agent-validation-design-2026-10-20.md): feasibility/design, not benchmark results.
