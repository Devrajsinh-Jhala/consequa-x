# Contributing to Consequa-X

Thanks for helping. This public repository holds the Python package, its tests
and documentation, the website, and the research records behind the paper. The
current release is on [PyPI](https://pypi.org/project/consequa-x/). It separates
a stable application evidence core from declared research interfaces (refund
simulation, programmatic policies, replay attribution and an optional local
Ollama adapter). Recorded studies establish declared implementation behavior,
not empirical superiority or a new causal estimator. Preserve original samples
when adding prompt profiles or evaluations.

Start with the [README](README.md), [design](docs/design.md), and
[research roadmap](docs/research-roadmap.md). The
[policy replay guide](docs/policy-replay.md) covers bounded context comparisons
and evidence exports. Release receipts under `output/release-*` record the exact
artifacts and installation checks for each published version.

Use a [GitHub issue](https://github.com/Devrajsinh-Jhala/consequa-x/issues/new/choose)
to discuss a larger adapter, schema change, new domain, or study before investing
in the implementation. Small fixes and reproducible bug reports can go straight
to a pull request. Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md), never in a public issue.

## Set up a development environment

Fork and clone the repository, then create a branch for your change. Use Python 3.11 or 3.12:

```sh
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS/Linux or `.\.venv\Scripts\Activate.ps1` in PowerShell. Then install the project and tools:

```sh
python -m pip install -e ".[dev]"
```

For the pinned Python 3.12 development dependencies, install `requirements-dev.lock` first, then install the project with `python -m pip install -e .`. Release receipts record the exact environments checked; the lock alone does not establish compatibility with another interpreter or platform.

Run the checks before submitting:

```sh
python -m pytest
python -m ruff check src tests
python -m build
```

GitHub Actions is currently disabled for this repository. Automatic push and
pull-request triggers have been removed; use the local checks above. The retained workflow is manual only and must not be re-enabled
or dispatched without the maintainer's authorization. Its configured test matrix
does not establish a current test result. Local release checks include fresh
package installations and access to the bundled trace schema.

## Where changes belong

| Location | Purpose |
| --- | --- |
| `src/consequa_x/` | Public records, validation, verification, graphs, explanations, attribution, and CLI |
| `src/consequa_x/benchmark/` | Offline simulator, scenarios, and replay runner |
| `src/consequa_x/adapters/` | Provider policy adapters with strict visible-input boundaries |
| `src/consequa_x/schemas/` | Versioned portable trace schema |
| `tests/` | Behavioral, conformance, integration, and export checks |
| `docs/` | Contracts, architecture, research plan, and supporting documents |
| `output/research/` | Literature assessment and research notes |

Include a regression test when correcting a behavioral defect. Adapter tests should use fixtures or local mocks so the default suite runs without provider credentials, network calls, or paid inference. Explain any public API or trace-format change and update the relevant documentation and schema/conformance checks together.

Generate the fixture outputs locally when a change affects their behavior:

```sh
consequa-x demo --output output/my-demo --seed 0
consequa-x experiment --output output/my-experiments --samples 40 --seed 0
```

Choose a new or empty output directory for every run. The CLI preserves existing
evidence and refuses populated output paths, including the committed `output/demo`
and `output/experiments` snapshots. Compare new outputs with those historical
snapshots. Any proposed snapshot update must retain the original evidence and
include the generating command, seed, and relevant revision in the pull request.

## Preserve the evidence contract

- Keep tool responses, reported agent assessments, observed outcomes, and effect origin separate. A successful response does not establish a completed effect.
- Preserve `unknown` outcomes for insufficient, stale, incomplete, or malformed evidence. State adapter trust assumptions, including completeness, watermark, and provenance declarations.
- Keep evaluator truth, fault labels, and scenario labels outside policy and explainer inputs. Simulator truth can support evaluation, but cannot be evidence available to the evaluated policy.
- Keep replay isolated, align paired random draws, and preserve the target outcome contract under context interventions. Report unknown pairs and the distribution an estimate describes.
- Label graph edge meanings explicitly. Observed provenance and recency do not establish counterfactual necessity; signed replay effects are not normalized responsibility shares.

Use synthetic or appropriately shareable examples in issues and fixtures. Do not include credentials or real customer/payment records.

## Research contributions

Useful contributions include related-work corrections, stronger baselines, additional LLM policy adapters, held-out task designs, independent outcome-verification adapters, and reproducible evaluations. Start with the [policy evaluation guide](docs/policy-evaluation.md) and [proposed study protocol](docs/study-plan.md). An issue should state the research question, primary sources, proposed comparison, and evidence needed to support the claim.

For experiments, report the model/provider and version where applicable, task templates and splits, seeds, interventions, verifier and origin assumptions, sample size, uncertainty, abstention/error coverage, and budget. Compare methods with equivalent evidence and resources. Distinguish simulator fixture results from actual model results, and distinguish a framework improvement from a methodological novelty claim.

The [attribution calibration guide](docs/attribution-calibration.md) describes
the offline repeated-mechanism command and its compressed evidence exports.
Preserve the predeclared protocol and all refused trials when extending it.
Keep analytic reference labels separate from the production outcome adapter;
do not redesign intervals after viewing a retained study and score the same
study as an independent validation.

The research brief is a proposal. Its claims should be checked against the literature and results before appearing as findings in a paper.

## Submit a pull request

Keep each pull request focused. Describe the problem, resulting behavior, evidence or tests, and remaining limitations. Link a related issue when available. State which checks you ran and which you could not run. Submit only material you have permission to share. Contributions submitted for inclusion in this project are provided under its [MIT License](LICENSE).
