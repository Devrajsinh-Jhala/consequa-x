# Python stable release readiness

Status updated 15 October 2026 after public registry verification. The stable
evidence core is complete and [version 1.0.0 is public on PyPI](https://pypi.org/project/consequa-x/1.0.0/).
Both reviewed files were independently downloaded and hash/size checked, and a
fresh public-registry installation passed its offline smoke checks. The GitHub
repository remains private. GitHub Actions stayed disabled throughout release
validation and publication.

## Release identity

| Field | Current decision or verified checkpoint |
| --- | --- |
| Repository | `Devrajsinh-Jhala/consequa-x`, private |
| Public distribution / import / command | `consequa-x` / `consequa_x` / `consequa-x` |
| Released stable version | [1.0.0](https://pypi.org/project/consequa-x/1.0.0/) |
| Frozen runtime source | `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9` |
| Final distribution-build source | `85ce6c316838c995782aadc8c10770acc708339b`; all 36 runtime files match the runtime freeze |
| Repository integration | PR #8 merged as `708d064`, preserving the frozen source commits |
| License / author metadata | MIT / Devrajsinh Jhala |
| Python requirement | `>=3.11`; current validation hosts are Windows with Python 3.11/3.12 |
| Required runtime dependencies | None |
| Wheel interface assets | `py.typed` and versioned portable JSON schemas |
| Source-archive materials | Runtime source, examples, Markdown docs, tests and study scripts; large retained datasets, model weights and the IEEE manuscript are excluded |
| PyPI account | Maintainer-supplied `devraj0502`; stable production upload and public artifact verification succeeded |
| Publication / registry installation | [Publication receipt](../output/release-1.0.0-2026-10-15/publication.json) / [fresh registry-install receipt](../output/release-1.0.0-2026-10-15/registry-install.json) |

Runtime source, study source and final distribution-build source must be recorded
separately when documentation or packaging changes follow the runtime freeze.
Do not rewrite historical study identities to the final release hash. In
particular, the 24-episode local-model study retains its earlier candidate wheel
and module hashes.

The immutable public source archive contains the dated pre-publication checklist
from its build revision. This repository document records the subsequently
completed gates; published artifacts and their checksums have not been rewritten.

## Completed stable release gates

| Gate | Observed status at this checkpoint |
| --- | --- |
| Full frozen-source suite | Passed: 1,480 tests and 240 subtests in 435.95 seconds; covers core, CLI, research interfaces and artifact checks |
| Python 3.11 source conformance | Passed on Windows: 200 tests and 165 subtests; this is not an installed-wheel result |
| Stable-publisher helper | Passed: 20 additional mocked tests; receipt gates, partial/idempotent upload, production endpoint, registry identity and post-upload verification behavior |
| Final lint | Passed: [retained lint output](../output/release-1.0.0-2026-10-15/stable-final-lint.log) |
| Wheel built from source archive | Passed at build source `85ce6c3`: [build log](../output/release-1.0.0-2026-10-15/stable-final-build.log) and [reviewed checks](../output/release-1.0.0-2026-10-15/checks.json) |
| Strict metadata/rendering and archive inventory | Passed: [strict metadata output](../output/release-1.0.0-2026-10-15/stable-final-metadata.log) and [inventory](../output/release-1.0.0-2026-10-15/inventory.json), covering 42 wheel entries, 130 source-archive files and 122 Git source files |
| Fresh wheel installation outside source checkout | Passed on Windows Python 3.12.14: [receipt](../output/release-1.0.0-2026-10-15/wheel-install.json), 12 trace round-trips, all three outcomes and four artifact-adapter checks |
| Fresh source-archive build/installation | Passed independently on Windows Python 3.12.14: [receipt](../output/release-1.0.0-2026-10-15/sdist-install.json), the same 12 trace and four adapter checks |
| Installed-wheel Python 3.11 conformance | Passed on Windows Python 3.11.9: 200 tests plus 165 subtests; [test evidence](../output/release-1.0.0-2026-10-15/stable-installed-python311-tests.xml) and [installation smoke](../output/release-1.0.0-2026-10-15/python311-install.json) |
| Public stable upload | Completed: [PyPI 1.0.0](https://pypi.org/project/consequa-x/1.0.0/) and [publication receipt](../output/release-1.0.0-2026-10-15/publication.json) |
| Public metadata, filename, size and SHA-256 verification | Passed for both files, including independent downloads: [receipt](../output/release-1.0.0-2026-10-15/publication.json) |
| Fresh public-registry installation and offline smoke | Passed on Windows Python 3.12.14: [receipt](../output/release-1.0.0-2026-10-15/registry-install.json), 12 trace round-trips, four adapter checks and all 36 frozen runtime payloads matched |

Use the exact reviewed wheel and source archive, not files rebuilt after their
hashes were recorded. Inspect the archive inventory for intended modules,
schemas, typing marker, license, CLI entry point, examples and documentation,
and for absence of credentials, private customer records, model weights and
unintended temporary files. A successful upload does not replace installation
or compatibility checks.

The stable uploader requires all named local gates to be exactly true and a
full frozen source revision. It checks two reviewed basenames, contained paths,
byte sizes and SHA-256 hashes before credentials are needed. Production PyPI
metadata must identify the intended project/version, and existing public files
must match reviewed names, sizes and hashes. Matching files are skipped rather
than replaced. An accepted upload without public verification remains pending.
The completed registry verification downloaded the published files, confirmed
the reviewed hashes, imported outside the checkout, accessed the bundled schema
and ran the offline application/trace smoke checks. All installations had zero
required runtime dependencies and made no model calls.

| Published artifact | Bytes | SHA-256 |
| --- | --- | --- |
| `consequa_x-1.0.0-py3-none-any.whl` | 151,622 | `32880f4c808705d1199db687c9fcc083b6e08e6ae9dd931d00c5335caaa06f5d` |
| `consequa_x-1.0.0.tar.gz` | 352,389 | `05162e12de85652def8c468ee8133d8c5e4f6c01f433da571373d71936ca26f0` |

The tested Windows interpreters do not establish Linux/macOS support results or
results for every Python newer than 3.12. Release receipts must give exact
interpreter versions and distinguish full tests, source conformance, installed
artifact checks and registry installation. Optional audit/plotting tools are
not framework runtime dependencies. No model download or paid inference is
required for release checks.

## Verified alpha checkpoint

The [alpha release checks](../output/release-alpha-2026-10-14/checks.json) bind
`0.1.0a2` to runtime source `40fa9bc7612c249dc33899a2ad6a6a12b5087ec4`.
The [publication receipt](../output/release-alpha-2026-10-14/publication.json)
records the accepted production upload, independent hash/size downloads and a
fresh registry installation with offline smoke checks on 14 October 2026.
Both alpha files are published on PyPI. Its earlier GitHub prerelease is now
subject to the repository's private access. These are completed alpha results,
not substitutes for the distinct version `1.0.0` gates above.

## Research and paper status

The retained [384-trial interval comparison](../output/interval-comparison-2026-10-13/FINDINGS.md)
reports coverage alongside width and detection costs. Conservative bounds do not
make unknown evidence or invalid intervention games numerically defined.
The [24-episode Qwen3 validation](../output/local-validation-2026-10-14/FINDINGS.md)
used 59 local model calls on exposed validation cases. The revised prompt
abstained in every structured status: its conditional contradiction rate is
undefined, and some rationales still made positive processing claims. No
improved accuracy, held-out generalization or baseline superiority is established.

The new repeated physical-interaction study is in progress under a predeclared
2,048-trial protocol, totaling 655,360 planned branches. It must finish and pass
its independent audit before its results are described as achieved. It calls
synthetic policies, not a language model. [Completion scope](completion-plan.md)
tracks the separate IEEE manuscript, source, references and checked-PDF gates.
A stable software release does not establish a new causal estimator or a
calibrated live-model confidence claim.

No npm package is published. An optional later adapter needs a declared API,
shared schema/conformance fixtures, cross-language integer/identity semantics,
installation tests and its own registry authorization and release receipt.
