# Completion target

The maintainer asked to finish the framework and paper beyond an alpha on
14 October 2026. The Python package is the first distribution; a second npm
implementation is optional future work. The paper will use the standard IEEE
conference format until a specific venue is selected.

Status updated 15 October 2026. The repository is private, and the maintainer has
explicitly authorized public stable PyPI publication. Alpha `0.1.0a2` is already
publicly published and independently verified. Version `1.0.0` is the current
candidate; its source version does not establish completed publication.

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

The remaining release gates are final wheel/sdist metadata and inventory checks,
independent fresh installations, installed-wheel Python 3.11 conformance, public
PyPI upload, matching public hashes/sizes and a fresh registry installation.
Record actual interpreters and hosts; Windows source checks do not imply results
on Linux, macOS or every newer Python. Do not run or enable GitHub Actions.
See [release readiness](release-readiness.md) for the gate status and receipts.

The refund benchmark and its replay experiments remain declared research
adapters. Stable core support does not imply a production payment integration,
authenticated evidence source or universal replay adapter.

## Finished paper

The supported contribution is an evidence/intervention protocol and reproducible
software artifact, with audited synthetic and exploratory local-model results.
The final manuscript will retain the original research brief as motivation and
describe the actual implemented scope.

The repeated physical-interaction sampling implementation, deterministic
serial/parallel conformance checks and independent auditor are complete. A
predeclared 2,048-trial retained run is in progress, with 655,360 planned branch
slots, explicit references/refusals and no language-model calls. The frozen
protocol is retained in `output/interaction-sampling-2026-10-15/protocol.json`;
no completed or audited result is claimed yet.

Finish that run without replacement draws, independently audit its saved
evidence, and integrate the achieved results into the manuscript. Complete the
discussion, refresh primary related-work sources, and compile/render the editable
IEEE LaTeX to a checked PDF. Retain scripts, protocols and data with their actual
source revisions. The source archive distributes software/examples/documentation;
retained datasets and the IEEE manuscript stay in the private repository.

Unimplemented joint context/fault methods, matched live baselines and broad
held-out generalization will be stated as future work. The manuscript will not
claim estimator novelty, causal necessity from provenance links, calibrated
live-model confidence or demonstrated superiority. The earlier validation family
is exposed; its results do not become held-out evidence by relabeling them.

Submission requires the maintainer's later choice of actual venue and confirmed
author/affiliation information. Preparing a complete IEEE paper does not imply
acceptance or submission to a venue.
