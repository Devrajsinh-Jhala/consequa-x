# Completion target

The maintainer asked to finish the framework and paper beyond an alpha on
14 October 2026. The Python package is the first distribution; a second npm
implementation is optional future work. The paper will use the standard IEEE
conference format until a specific venue is selected.

## Stable framework

Completion means an installable release that another developer can use without
the refund simulator: capture logical actions, attempts, responses and reported
assessments; attach independently obtained observations through an explicit
verifier; preserve unknown outcomes and separate origin; export/import a valid
trace; and generate an evidence graph and explanation.

Before marking the release stable:

- Fix conflicting successive effect witnesses in evidence graphs.
- Validate domain-specific explanation details with controlled error handling.
- Add an explicit custom verifier and domain-neutral explanation path, with a
  complete non-refund application example and meaningful conformance checks.
- Preserve existing evidence in every public CLI command's output handling.
- Document the supported core API, trace schema and graph migration behavior.
- Validate the final wheel and source distribution in isolated installations,
  record the interpreters/platforms actually checked, and keep broader limits
  explicit. Do not run or enable GitHub Actions.
- Publish the reviewed stable artifacts and verify the public hashes and a fresh
  registry installation. A version change alone does not satisfy this target.

The refund benchmark and its replay experiments remain declared research
adapters. Stable core support does not imply a production payment integration,
authenticated evidence source or universal replay adapter.

## Finished paper

The supported contribution is an evidence/intervention protocol and reproducible
software artifact, with audited synthetic and exploratory local-model results.
The final manuscript will retain the original research brief as motivation and
describe the actual implemented scope.

Add repeated physical-interaction sampler validation using a protocol frozen
before execution, all planned draws and explicit reference/refusal denominators.
Audit the saved evidence independently. Integrate the achieved results, complete
the discussion, refresh primary related-work sources, and produce editable IEEE
LaTeX and a checked PDF. Retain scripts, protocols and data with source revisions.

Unimplemented joint context/fault methods, matched live baselines and broad
held-out generalization will be stated as future work. The manuscript will not
claim estimator novelty, causal necessity from provenance links, calibrated
live-model confidence or demonstrated superiority. The earlier validation family
is exposed; its results do not become held-out evidence by relabeling them.

Submission requires the maintainer's later choice of actual venue and confirmed
author/affiliation information. Preparing a complete IEEE paper does not imply
acceptance or submission to a venue.
