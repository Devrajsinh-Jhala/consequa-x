# Completion target

**Historical scoped status.** The current external-validation completion gates
are in [the 22 October criteria](paper-completion-criteria-2026-10-22.md).
Earlier completion statements below describe their dated software/protocol
scope; they do not establish completion of the stronger research study requested
after review. No human review is required by the current automated-only study.

The maintainer asked to finish the framework and paper beyond an alpha on
14 October 2026. The Python package is the first distribution; a second npm
implementation is optional future work. The paper will use the standard IEEE
conference format until a specific venue is selected.

Status updated 16 October 2026. The stable evidence
core is complete: [version 1.0.0 is public on PyPI](https://pypi.org/project/consequa-x/1.0.0/),
with both published artifact downloads independently hash/size checked and a
fresh registry installation verified. The repository remains private. The
retained collection, its independent audit and checked IEEE paper are complete.
The defined framework and protocol/software paper scope was achieved on
16 October 2026. Venue selection, final human review, reviewer access and
submission remain separate maintainer steps.

## Stable framework

Completion means an installable release that another developer can use without
the refund simulator: capture logical actions, attempts, responses and reported
assessments; attach independently obtained observations through an explicit
verifier; preserve unknown outcomes and separate origin; export/import a valid
trace; and generate an evidence graph and explanation.

The runtime implementation is complete and frozen at
`0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`: successive graph witnesses, explicit
verifiers and target matching, controlled domain/type errors, a full non-refund
application example, preserved CLI evidence, and the core/schema compatibility
contract are implemented. The frozen-source suite passed 1,480 tests plus 240
subtests. Windows Python 3.11 source conformance passed 200 tests plus 165 subtests;
twenty additional stable-publisher tests passed.

All release gates passed for build source
`85ce6c316838c995782aadc8c10770acc708339b`, whose 36 runtime files match that
freeze. Final metadata/inventory checks, independent Windows Python 3.12.14
wheel/sdist installations, installed-wheel Python 3.11.9 conformance (200 tests
plus 165 subtests), public upload and downloaded hash/size verification are
recorded in [release readiness](release-readiness.md). The
[fresh registry installation](../output/release-1.0.0-2026-10-15/registry-install.json)
passed 12 trace round-trips and four artifact-adapter checks without model calls.
PR #8 is merged as `708d064`, preserving the runtime and build freezes. Windows
checks do not imply results on Linux, macOS or every newer Python. GitHub Actions
stayed disabled. The immutable public archive retains its dated build-time status
documents; subsequent publication receipts do not change the reviewed artifacts.

The refund benchmark and its replay experiments remain declared research
adapters. Stable core support does not imply a production payment integration,
authenticated evidence source or universal replay adapter.

## Finished paper

The supported contribution is an evidence/intervention protocol and reproducible
software artifact, with audited synthetic and exploratory local-model results.
The completed manuscript retains the original research brief as motivation and
describes the actual implemented scope.

The repeated physical-interaction sampling implementation, deterministic
serial/parallel conformance checks and independent auditor are complete. A
predeclared run completed collection on 15 October 2026, retaining all 2,048
trials and 655,360 planned branch slots. It used 628,535 scripted policy calls,
zero model calls and zero additional comparison calls. The
[protocol](../output/interaction-sampling-2026-10-15/protocol.json),
[summary](../output/interaction-sampling-2026-10-15/summary.json) and
[execution receipt](../output/interaction-sampling-2026-10-15-execution.json)
retain source `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9` and the installed
checkpoint identity. Every planned slot remains present, including invalid,
failed and unstarted outcomes. The
[independent saved-evidence audit](../output/interaction-sampling-audits-2026-10-15/independent.json)
passed 44,698,925 assertions on all planned trials/branches and 4,210 preselected
complete traces. Its receipt binds the sealed export manifest. The
[derived findings](../output/interaction-sampling-findings-2026-10-15/FINDINGS.md)
and complete tables preserve availability, population eligibility, interval
coverage, width, detection and refusals; they do not establish broad calibration
or superiority.

The independently checked results are integrated into the completed
protocol/software manuscript. The
[eight-page illustrated IEEE PDF](../output/pdf/Consequa-X_IEEE_Paper.pdf) compiled successfully
and every rendered page passed visual review on 16 October 2026. Its
[QA receipt](../output/pdf/qa.json) binds the PDF hash and exact
[editable IEEE source](../paper/consequa-x-ieee.tex) and four
[vector figures](../paper/figures/README.md); fonts are embedded and checks found
no missing characters, unresolved references or overfull boxes. Scripts,
protocols and data retain their actual source revisions. The public source
archive distributes software/examples/documentation; retained datasets and the
IEEE manuscript stay in the private repository.

The [hard-launch plan](launch-readiness.md) describes proposed usability and
adoption improvements for a bounded next release: an offline report with minimal
disclosure, public onboarding/support and real additional-platform checks.
Those features are not included in the published 1.0.0 package.

Unimplemented joint context/fault methods, matched live baselines and broad
held-out generalization will be stated as future work. The manuscript will not
claim estimator novelty, causal necessity from provenance links, calibrated
live-model confidence or demonstrated superiority. The earlier validation family
is exposed; its results do not become held-out evidence by relabeling them.

Submission requires the maintainer's later choice of actual venue and confirmed
author/affiliation information. Preparing a complete IEEE paper does not imply
acceptance or submission to a venue.
