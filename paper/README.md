# ConseqaX research paper

[conseqax-research.tex](conseqax-research.tex) is the current primary generic IEEE
manuscript; [conseqax-research.md](conseqax-research.md) is its readable companion.
It centers an evidence protocol and a controlled software/systems evaluation of
ambiguous-action recovery. The author is Devrajsinh Jhala, **Independent
Researcher**. No specific conference or journal has been selected, and a contact
email has not been supplied.

The [checked 10-page PDF](../output/pdf/recovery-study-editorial-2026-10-21/ConseqaX_Research_Paper.pdf)
is accompanied by exact source/figure copies, compile diagnostics, all-page
previews, and byte-bound evidence references in the same snapshot directory.
It is a complete generic IEEE draft; venue-specific length, anonymity, contact,
and submission requirements remain to be applied after a venue is selected.
This editorial revision corrects source-independence wording and adds explicit
versioned reference links. It adds no experimental outcomes. The
[original sealed 20 October build](../output/pdf/recovery-study-2026-10-20/ConseqaX_Research_Paper.pdf)
is preserved.

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

## Native autonomous external pilot in development

The [automated workflow](../docs/native-external-benchmark.md) implements four
matched native airline conditions on twelve prespecified task IDs (48 planned
slots), local inference, required native DB/communication grading, complete
request/tool capture and offline replay. All 190 benchmark-infrastructure tests
pass; a further 20 tests cover the auxiliary resource observer.

The first unmodified development episode returned 14 model completions and
five actual tools. Its [independent saved-artifact audit](../output/native-development-2026-10-21/native-19-000-audit/audit-result.json)
passed; native task reward was **0**, and its empty communication requirement
passed vacuously. This establishes integration, not framework benefit. Later
development checks fix and retain hidden SDK retry and null-serialization
issues before any official collection. Exact-source native and guarded
readiness checks remain in progress; there is no official pilot result yet.
GitHub Actions stays disabled, with no human review or paid inference.

## Product version and evidence boundaries

The published product is **2.1.2**, with a retained
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
The focused manuscript requires its own final compilation and visual-quality
receipt after its results are integrated. A document-quality check establishes
neither scientific validity nor venue-specific submission compliance.

## Remaining research and submission work

External validation still needs actual autonomous-agent decisions with native
benchmark reward, matched classical controls, and an independently checked
side-effect ledger. Adapter predicates, source authority, and provider
finality/idempotency assumptions need independent service or ground-truth
validation. More internal seeds cannot fill those gaps. Methodological novelty,
transfer beyond the controlled substrate, and the limits of prior-work overlap
remain substantive questions.

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
