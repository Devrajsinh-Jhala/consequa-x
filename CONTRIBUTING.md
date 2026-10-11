# Contributing to Consequa-X

Contributions to the Python framework and the research are welcome. This is an alpha: the implementation uses refund simulation, programmatic policies, and an optional local Ollama adapter. Recorded results include scripted fixtures and a small [local-model pilot](output/live-pilot-2026-10-10/README.md). These establish implementation behavior, not empirical superiority or a new causal estimator. Preserve original live samples when adding exploratory prompt profiles or new evaluations.

Start with the [README](README.md), [design](docs/design.md), and [research roadmap](docs/research-roadmap.md). The [policy replay guide](docs/policy-replay.md) covers bounded context comparisons and evidence exports. Use an issue to discuss a larger adapter, schema change, new domain, or study before investing in the implementation. Small fixes and reproducible bug reports can go straight to a pull request.

## Set up a development environment

Fork the repository, clone your fork, and create a branch for your change. Use Python 3.11 or 3.12:

```sh
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS/Linux or `.\.venv\Scripts\Activate.ps1` in PowerShell. Then install the project and tools:

```sh
python -m pip install -e ".[dev]"
```

For the pinned development dependencies used in CI, install `requirements-dev.lock` first, then install the project with `python -m pip install -e .`. The lock records the initial Python 3.12 environment; CI checks it on both supported versions.

Run the checks before submitting:

```sh
python -m pytest
python -m ruff check src tests
python -m build
```

CI runs tests, lint, and package builds on Ubuntu and Windows with Python 3.11 and 3.12. A wheel installation check verifies that the bundled trace schema is available. CI does not publish packages to a registry.

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
consequa-x demo --output output/demo --seed 0
consequa-x experiment --output output/experiments --samples 40 --seed 0
```

These outputs are reproducible snapshots. If you propose updating committed snapshots, include the generating command, seed, and relevant revision in your pull request.

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

The research brief is a proposal. Its claims should be checked against the literature and results before appearing as findings in a paper.

## Submit a pull request

Keep each pull request focused. Describe the problem, resulting behavior, evidence or tests, and remaining limitations. Link a related issue when available. State which checks you ran and which you could not run. Submit only material you have permission to share. Contributions submitted for inclusion in this project are provided under its [MIT License](LICENSE).
