# Consequa-X 1.0.0 release evidence

The stable package is publicly published at
https://pypi.org/project/consequa-x/1.0.0/. The GitHub repository stays private.
GitHub Actions was disabled throughout; all checks ran locally on Windows.

`checks.json` is the immutable pre-upload gate receipt. It identifies the exact
wheel/source archive, all eight achieved checks, source/build revision
`85ce6c316838c995782aadc8c10770acc708339b`, and frozen runtime/study revision
`0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`. All 36 runtime files match. The
earlier study checkpoint is preserved separately and is not these final files.

`publication.json` records public PyPI metadata and independent downloads of
both files with exact SHA-256 and byte-size verification. `registry-install.json`
records the fresh public-index installation and its real offline workflows.
`github-release.json` records the private GitHub tag and downloaded release assets.
The initial upload succeeded; its first metadata poll encountered cached 404
responses. Public verification then succeeded without another upload, and the
idempotent uploader subsequently recognized both existing files.

The full frozen-source run passed 1,480 tests and 240 subtests. Twenty additional
publisher tests passed. The final installed wheel passed 200 tests and 165
subtests on isolated Python 3.11.9, with the checkout import path removed and
tests/examples taken from the shipped source archive. Separate clean Python
3.12.14 wheel and source-archive installations passed 12 trace roundtrips,
all three outcome statuses and four artifact-application checks. The installed
CLI preserved existing evidence and completed a separate two-worker engineering
smoke; that smoke is excluded from the retained research study.

`inventory.json` checks every shipped Git source file, exact permitted generated
metadata, every runtime file, wheel RECORD entries, MIT license, schema, typing
marker, CLI entry point and dependency metadata. `inventory-recheck.json` is the
identical result after correcting the retained auditor's repository-root lookup.
The retained auditor can run from this directory with a new scratch directory
containing copies of the two reviewed artifacts; it refuses to replace an
existing inventory. Installation and CLI validators also require new output
paths and explicit installed-root/source identities. Logs and JUnit results are
retained beside these receipts. Do not replace an achieved receipt to record a
different run.

No Linux/macOS or newer-interpreter test result is implied. The source archive
contains documentation, examples, tests and research scripts; private retained
datasets, the IEEE paper, credentials and model weights are not packaged. Stable
core support does not establish a new estimator, live-model calibration or
attribution superiority. The separately frozen 2,048-trial research study has its
own protocol, source identity, evidence and independent audit.
