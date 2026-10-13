# Python alpha release readiness

Drafted 13 October 2026. The first distribution target is PyPI. A later npm
adapter can share trace schemas and conformance fixtures after the Python
interface settles. A registry alpha is an engineering release; it does not
require or establish research-paper superiority.

## Known release identity

| Field | Current source metadata or decision |
| --- | --- |
| Repository | [Devrajsinh-Jhala/consequa-x](https://github.com/Devrajsinh-Jhala/consequa-x), public |
| License | MIT |
| Maintainer/author metadata | Devrajsinh Jhala |
| Distribution name | `consequa-x`; project API returned 404 on 13 October 2026, which does not establish name claimability or ownership |
| Python import | `consequa_x` |
| Command | `consequa-x` |
| Current alpha metadata | `0.1.0a2`; bind the actual final build to its frozen source revision |
| Python requirement | `>=3.11`; classifiers currently list 3.11 and 3.12 |
| Runtime dependencies | None required in current `pyproject.toml` |
| Included interface assets | `py.typed` and bundled JSON trace schemas |
| PyPI account | Maintainer supplied `devraj0502`; [official public profile](https://pypi.org/user/devraj0502/) displays Devrajsinh Jhala. Project ownership and working upload authentication remain unestablished. |

## Required local release checks

Freeze a clean source revision for the chosen alpha and record that revision,
version, local validation environment and wheel/sdist SHA-256 hashes. Keep study
source revisions distinct from the release revision. A new public version must
accurately describe API, default-interval and intervention-game changes.

Before registry upload, complete and retain:

- Appropriate local tests and lint for the final changes, with actual pass/fail
  output. Earlier successful counts do not validate later edits.
- Wheel and source distribution builds, metadata/rendering checks and inspection
  of included files, license, schemas, entry point and typing marker.
- Fresh-environment wheel installation outside the source checkout, followed by
  import/CLI and offline exported-trace round-trip smoke checks. Confirm the
  installed artifact, rather than an accidentally imported working-tree package.
- A corresponding source-distribution build/install check, so third parties can
  reconstruct the wheel without relying on ignored local files.
- Manual checks for the Python/platform compatibility being promised. If a clean
  interpreter or host is unavailable, record that limitation rather than implying
  a new compatibility result.
- Review of the packaged file inventory for secrets, personal customer data,
  model weights and unintended temporary files. Retained study data must remain
  synthetic and clearly distinguish evaluator truth from explainer evidence.
- Release notes describing alpha stability, source trust, replay/refusal
  semantics, individual interval assumptions and known research limits.

The current framework has zero required runtime dependencies; optional local
research/audit/plotting tools do not become runtime dependencies merely because
they were used to validate a study. Ollama inference requires an existing local
server/model, but an import and scripted offline run must work without a paid
provider or model download.

**GitHub Actions stays disabled.** The maintainer has exhausted its quota and
asked that Actions not be used. Run validation and build checks locally; do not
dispatch a workflow or re-enable automation for this release.

## Registry operations still required

The public profile check confirmed the supplied username and display name on
13 October 2026. A read-only check of the
[official project API](https://pypi.org/pypi/consequa-x/json) returned 404 that day.
That establishes that no public project record was returned by that endpoint;
it does not prove the name is claimable or establish account ownership of it.
Standard local environment and `.pypirc` checks found no configured upload
authentication. A working secure authentication path remains necessary.

Check the intended project's name/ownership in the maintainer's PyPI account.
Having an account does not establish that this distribution name can be created
or updated. Then use the actual reviewed artifacts and the maintainer's secure
secure upload authentication. Keep credentials out of chat, source, shell output,
study exports and release manifests. This document neither requests credentials
nor creates or modifies authentication.

A TestPyPI rehearsal is optional and separately scoped: it uses a separate
service/account and does not establish production PyPI ownership. If used, record
which artifact was tested, install it into a fresh environment and keep production
and test release records distinct. The
[official Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
describes the wheel/sdist and upload workflow; the chosen tool/configuration must
still be validated on this release's host.

After the actual production upload, verify the public version and metadata,
download/install the registry artifact in a clean environment, compare its hash
with the retained artifact, and run the same offline smoke checks. Record the
public project/version link, tag/revision and final release checks. Until then,
describe the package as source-installable or locally built, not publicly
published on PyPI.

## Release receipt template

Complete this record with actual observed values; blank fields are pending.

| Item | Value |
| --- | --- |
| Version / source revision / tag | Pending final freeze |
| Python, operating system, build tooling | Pending local release record |
| Local tests and lint | Pending final validation |
| Wheel file and SHA-256 | Pending artifact build/check |
| Sdist file and SHA-256 | Pending artifact build/check |
| Fresh wheel and sdist installation results | Pending checks |
| Tested compatibility and known limits | Pending record |
| Package inventory and metadata check | Pending check |
| Account identity | `devraj0502`, public display name Devrajsinh Jhala, checked 13 October 2026 |
| Name/owner verification | Public project API 404 on 13 October 2026; name claimability/ownership pending |
| Upload authentication | No configured standard local upload authentication found; working path pending |
| Production upload and registry installation | Pending |
| Public release URL | Pending actual upload |

## Research and npm follow-up

The [working paper](../paper/manuscript.md) separates completed synthetic/local
integration evidence from pending held-out comparisons. A public alpha should
carry those same claim limits. The package must not advertise calibrated
language-model confidence, live baseline superiority or broad domain validation
that the retained evidence does not establish.

This alpha's release notes should state its conservative default changes:
Clopper-Pearson for conditional binary contrastive effects, Hoeffding for signed
Shapley pair means and split-allowance exact binomial endpoint differences.
Legacy bootstrap/normal methods remain explicit options and frozen calibration
comparators. The [audited comparison](../output/interval-comparison-2026-10-13/FINDINGS.md)
retained 384 new trials and found a substantial interval-width/detection tradeoff.
The strict intervention game's semantics remain unchanged; conservative bounds
do not make invalid games or unknown evidence numerically defined.

For npm, first specify the adapter's scope, schema compatibility/versioning,
cross-language money/time/identity semantics and shared conformance fixtures.
Confirm the intended package name, ownership and release authentication only when
an installable adapter is ready. No npm package or registry release is claimed
by the current Python implementation.
