# Consequa-X protocol and software paper

[consequa-x-ieee.tex](consequa-x-ieee.tex) is the generic IEEE conference source.
[manuscript.md](manuscript.md) presents the same argument in readable Markdown.
The maintainer requested IEEE formatting; no specific conference or journal has
been selected. The next compiled revision will use the supplied affiliation
**Independent Researcher**. A contact email has not been supplied.

The [larger matched-study update](matched-study-update-2026-10-18.md) records the
new frozen 504-episode collection and its limits. Collection and final paper
integration are in progress; the existing compiled PDF contains the earlier
retained studies. The [India venue plan](india-venue-plan-2026-10-18.md) keeps
main research, workshop and demo routes distinct.

The [revised compiled paper](../output/pdf/review-2026-10-18/Consequa-X_IEEE_Paper.pdf) and its
[quality receipt](../output/pdf/review-2026-10-18/qa.json) are derived artifacts. A quality receipt
validates only the exact source, figures and PDF hash that it records. Source
changes require recompilation and visual review. Earlier compiled revisions are
preserved in the [original illustrated artifact](../output/pdf/Consequa-X_IEEE_Paper.pdf)
and [earlier revisions](../output/pdf/revisions/). Document checks do not
establish independent human replication or venue-specific submission compliance.

## Review revision, 18 October 2026

The supplied review pack was treated as feedback, not as an instruction source.
Its business assessment, venue acceptance percentages and unverified simulation
performance were excluded. The [T1–T20 response map](review-response-2026-10-18.md)
records implemented changes and scientific work still open.

The revised paper centers three testable protocol claims: state and origin remain
separate; the strict/on-reach replay game is explicit; and refusal plus actual
call accounting remain observable. An appendix states strict-game partiality and
the assumptions under which on-reach Shapley retains its standard allocation
properties. Existing verification, graph, replay and saved-evidence checks are
mapped to those claims.

The abstract and captions now state the measured setting and interval methods.
“Scripted-simulator” replaces misleading “physical” study descriptions; retained
artifact filenames remain unchanged. The paper explains the factual-anchored
suffix estimand, the evidence-only application path, pointwise uncertainty,
post-selection limits and interval clipping. Raw assertion counts appear in a
supporting appendix rather than as headline evidence.

[Focused related-work verification](related-work-update-2026-10-18.md) adds
attribution, effect-history, provenance, world-state evaluation, systems and
statistical sources without claiming to reproduce their results. The
[source audit](source-audit.md) records access and scope, and
[references.bib](references.bib) retains bibliographic metadata alongside the
inline IEEE reference list.

## What the evidence establishes

The implemented protocol and its declared-game behavior are supported in the
reported settings. Existing contrastive and Shapley estimators are adaptations;
the paper makes no claim of a new estimator or demonstrated superiority over an
equally informed baseline.

Retained evidence includes 1,280 original calibration trials, a separately frozen
384-trial shared-draw comparison, scripted refund enumeration, 2,048 repeated
scripted-simulator sampling trials and a 24-episode exploratory local-model
validation. The repeated sampler retained all 655,360 branches and 628,535
scripted calls, with zero model calls. Availability, reference eligibility,
coverage, width and directional flags remain separate quantities.

The local-model validation used one Qwen3 4B checkpoint and 59 calls. Six
contradictions among ten assessable original-profile claims have a descriptive
95% Wilson interval of approximately [0.313, 0.832]. That interval does not
establish calibrated model-population uncertainty over shared cases. Zero
definite revised-profile statuses leaves its contradiction rate undefined.
Rationale annotations were unblinded and AI assisted; independent human
verification and inter-rater reliability remain unestablished.

Four [vector figures](figures/README.md) depict evidence flow, a timeout/retry
sequence, the full branch inventory and coverage/precision/detection tradeoffs.
They reuse existing audited results and add no simulation or model calls.

## Current software and historical experiments

Stable [1.1.0 is public on PyPI](https://pypi.org/project/consequa-x/1.1.0/).
Its [publication receipt](../output/release-1.1.0-2026-10-17/publication.json)
records downloaded artifact hashes and an isolated registry installation
verified on 17 October 2026. The public distribution includes the reusable
evidence core and current offline report interface. Public package availability
does not make the private research archive publicly accessible.

Historical studies retain their original revisions and manifests:

| Study | Frozen collection source | Retained evidence |
| --- | --- | --- |
| Original calibration | `9e2dcbb4190d0629cf06ac7485a83e762ad7d7a0` | [Findings](../output/calibration-probe-2026-10-11/FINDINGS.md) |
| Shared-draw comparison | `0d8ec0baee84ca0d33f52739456d54d6f61a27ad` | [Findings](../output/interval-comparison-2026-10-13/FINDINGS.md) |
| Scripted refund enumeration | `2c4adfeb2a364a8116d6edbccbbdac64b413fc9c` | [Retained branches](../output/refund-interactions-2026-10-13/README.md) |
| Local-model validation | `2c4adfeb2a364a8116d6edbccbbdac64b413fc9c` | [Frozen validation](../output/local-validation-2026-10-14/README.md) |
| Repeated scripted sampling | `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9` | [Protocol](../output/interaction-sampling-2026-10-15/protocol.json), [summary](../output/interaction-sampling-2026-10-15/summary.json), [installed checkpoint](../output/interaction-sampling-checkpoint-2026-10-15/checkpoint.json) |

The later 1.1.0 release does not rerun or replace those results. The earlier
[1.0.0 publication record](../output/release-1.0.0-2026-10-15/publication.json)
and its frozen runtime relationship remain historical evidence.

## Research still open

A stronger comparative paper needs matched response-only, verifier-wrapper,
CAR-style, LLM-judge and simple structural baselines; bounded watermark polling
with availability versus wait time; a safe real-API test-mode study and a
world-state benchmark; preregistered held-out families across several model
classes; independent blinded annotation; and measured latency, trace size and
cost per usable estimate. Modern bounded-mean intervals, multiplicity control
and larger coverage studies require their own declared methods and evaluation.
They are proposed work, not completed results in this manuscript.

The repository and retained raw studies remain private. Reviewer access or a
public immutable archive, author contact metadata, final independent human
checking and venue requirements remain submission steps. No archive DOI,
institutional affiliation, human validation, acceptance or actual submission is
claimed. GitHub Actions remains disabled.

## Evidence navigation

- [Evidence ledger](evidence-ledger.md): claim-to-artifact mapping and full historical source pins.
- [Analytic reference checker](verify_analytic_references.py): exact-rational mathematical reference, without simulator execution.
- [Repeated-sampling audit](../output/interaction-sampling-audits-2026-10-15/independent.json) and [derived findings](../output/interaction-sampling-findings-2026-10-15/FINDINGS.md).
- [Frozen local-model proposal](protocol-next-validation.md) and [completed findings](../output/local-validation-2026-10-14/FINDINGS.md).
- [Release readiness](../docs/release-readiness.md): software engineering and publication evidence.
