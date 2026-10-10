"""Offline demonstration, trace explanation, and fixture replay experiments."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from . import __version__
from .attribution import InsufficientEvidenceError, Intervention, leave_one_out
from .benchmark.runner import (
    RefundContext, RefundReplayRunner, ScenarioConfig, demo_scenarios, run_scenario,
)
from .explanation import explain
from .models import Trace, to_dict
from .schema import get_trace_schema


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def _demo(args):
    output = Path(args.output)
    rows = []
    manifest = []
    cases = []
    for index, config in enumerate(demo_scenarios()):
        episode = run_scenario(config, seed=args.seed + index)
        stem = f"episode_{index:02d}"
        paths = {
            "trace": output / "traces" / f"{stem}.json",
            "explanation": output / "explanations" / f"{stem}.json",
            "truth": output / "evaluator_truth" / f"{stem}.json",
        }
        _write_json(paths["trace"], episode.trace)
        _write_json(paths["explanation"], episode.explanation)
        _write_json(paths["truth"], {
            "scenario": config.name, "seed": episode.seed, "config": to_dict(config),
            "records": episode.ground_truth,
        })
        for path in paths.values():
            manifest.append({"path": path.relative_to(output).as_posix(),
                             "sha256": sha256(path.read_bytes()).hexdigest()})
        verification = episode.trace.verifications[-1]
        matching = verification.evidence[-1].details.get("matching_count", "unknown")
        rows.append(f"| {config.name} | {episode.trace.assessment.status.value} | "
                    f"{verification.status.value} | {verification.origin.value} | {matching} |")
        cases.append({"scenario": config.name, "trace": paths["trace"].relative_to(output).as_posix(),
                      "explanation": paths["explanation"].relative_to(output).as_posix(),
                      "diagnosis": episode.explanation.diagnosis})
    _write_json(output / "evaluator_truth" / "cases.json", cases)
    _write_json(output / "trace-schema.json", get_trace_schema())
    _write_json(output / "manifest.json", {"package_version": __version__, "artifacts": manifest})
    summary = (
        "# Consequa-X: first offline demo\n\n"
        "This demo uses transparent programmatic policies and local simulated money. "
        "The refund target is INR 5,000 (500,000 paise), exactly once, by the declared deadline.\n\n"
        "| Scenario | Agent reported | Verified outcome | Effect origin | Matching effects |\n"
        "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        "The timeout-after-commit case diagnoses **BELIEF / RESPONSE DIVERGENCE**. "
        "The unsafe retry produces two partial refunds within the payment's original "
        "INR 10,000 balance. The safe retry reuses a key and produces one effect.\n\n"
        "The external-actor case satisfies the desired state while the agent's attempt "
        "failed. Its graph contains no provider-origin link from the agent's dispatch "
        "to the other actor's effect. Missing provenance yields unknown origin.\n\n"
        "Delayed readback stays unknown until its watermark covers the horizon. "
        "Synthetic compensation tests temporal contracts; it is not a claim about "
        "real-provider refund reversibility.\n\n"
        "`traces/` and `explanations/` contain portable evidence records. "
        "`evaluator_truth/` holds injection labels and simulator truth and must not "
        "be passed to an explainer. The manifest checks file integrity, not authenticity.\n"
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "README.md").write_text(summary, encoding="utf-8")
    print(f"Generated {len(cases)} offline scenarios in {output.resolve()}")
    for case in cases:
        print(f"  {case['scenario']}: {case['diagnosis']}")
    return 0


def _experiment(args):
    if args.samples < 20:
        raise ValueError("CLI research demonstrations require at least 20 samples per condition")
    output = Path(args.output)
    candidates = tuple(Intervention(name) for name in
                       ("vip_policy", "vip_memory", "retry_instruction", "distractor"))
    results = []
    rows = []
    configurations = (
        ScenarioConfig("deterministic_retry_fixture", context=RefundContext(retry_instruction=True),
                       use_idempotency=False),
        ScenarioConfig("stochastic_retry_fixture", context=RefundContext(retry_instruction=True),
                       use_idempotency=False, selection_probability=0.9, retry_probability=0.7),
    )
    for config in configurations:
        runner = RefundReplayRunner(config)
        for target in ("action", "consequence"):
            estimates = leave_one_out(runner, candidates, samples=args.samples, seed=args.seed, target=target)
            for estimate in estimates:
                lower, upper = estimate.confidence_interval
                rows.append(f"| {config.name} | {target} | {estimate.event_id} | "
                            f"{estimate.baseline_rate:.3f} | {estimate.intervention_rate:.3f} | "
                            f"{estimate.effect:+.3f} | [{lower:+.3f}, {upper:+.3f}] |")
            results.append({"config": to_dict(config), "policy_type": "programmatic_fixture",
                            "replay_mode": runner.mode, "target": target,
                            "estimates": to_dict(estimates)})
    _write_json(output / "results.json", {
        "package_version": __version__, "samples_per_condition": args.samples,
        "seed": args.seed, "results": results,
        "claim": "Prototype plumbing validation; no LLM evaluation or attribution-method superiority tested.",
    })
    summary = (
        "# Fixture replay experiment\n\n"
        f"{args.samples} paired replays per condition, initial seed {args.seed}. "
        "Each branch starts an isolated simulated world. All results use programmatic "
        "fixture policies, including the explicitly stochastic policy.\n\n"
        "| Fixture | Target | Neutralized context | Original rate | Changed rate | Signed effect | Approx. 95% interval |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        "The deterministic retry instruction changes initial action selection by 0, "
        "but changes exactly-once refund satisfaction by -1. Removing the instruction "
        "prevents a second committed refund. This validates that the two estimator "
        "targets can differ; it is not a new-method result.\n\n"
        "Positive signed effects mean neutralization reduced the target probability; "
        "negative effects mean it increased that probability. These values are not "
        "shares of responsibility. Intervals subtract Bonferroni-adjusted marginal "
        "Wilson bounds; coverage is approximate and conservative. They describe "
        "this replay distribution, not generalization across tasks. Unknown pairs "
        "refuse an estimate.\n\n"
        "Strong comparisons against verifier-plus-CAR, real stochastic LLM policies, "
        "and held-out task templates remain research work.\n"
    )
    (output / "README.md").write_text(summary, encoding="utf-8")
    print(f"Generated {len(results)} fixture comparisons in {output.resolve()}")
    return 0


def _explain(args):
    trace = Trace.from_json(Path(args.trace).read_text(encoding="utf-8"))
    result = explain(trace)
    if args.output:
        _write_json(Path(args.output), result)
        print(f"Saved explanation to {Path(args.output).resolve()}")
    else:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, allow_nan=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="consequa-x", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run offline divergence scenarios")
    demo.add_argument("--output", default="output/demo")
    demo.add_argument("--seed", type=int, default=0)
    demo.set_defaults(handler=_demo)
    experiment = commands.add_parser("experiment", help="Run paired fixture interventions")
    experiment.add_argument("--output", default="output/experiments")
    experiment.add_argument("--samples", type=int, default=40)
    experiment.add_argument("--seed", type=int, default=0)
    experiment.set_defaults(handler=_experiment)
    command = commands.add_parser("explain", help="Explain an existing trace without replay or writes")
    command.add_argument("trace")
    command.add_argument("--output")
    command.set_defaults(handler=_explain)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, TypeError, OSError, InsufficientEvidenceError) as error:
        print(f"consequa-x: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
