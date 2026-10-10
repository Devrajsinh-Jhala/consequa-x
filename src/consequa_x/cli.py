"""Trace explanation, offline replay, and bounded policy evaluations."""

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


def _model_eval(args):
    from .adapters.ollama import OllamaPolicy
    from .benchmark.evaluation import evaluate_policy, evaluation_sample_record
    from .benchmark.policy_runner import MAX_TRIAL_SEED
    from .policies import ScriptedRefundPolicy

    output = Path(args.output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("model-eval requires a new or empty output directory to preserve each evaluation")
    configurations = demo_scenarios()
    if args.cases:
        names = args.cases.split(",")
        by_name = {config.name: config for config in configurations}
        if any(name not in by_name for name in names) or len(set(names)) != len(names):
            raise ValueError("cases must be unique known demo names, separated by commas")
        configurations = tuple(by_name[name] for name in names)
    if args.provider == "ollama" and not args.model:
        raise ValueError("--model is required with --provider ollama")
    if args.provider == "scripted" and args.model:
        raise ValueError("--model requires --provider ollama; scripted is an offline fixture")
    # Validate the schedule before contacting a provider or writing artifacts.
    if args.samples < 1 or args.seed < 0 or args.max_calls < 1 or not 1 <= args.max_attempts <= 5:
        raise ValueError("samples/max-calls must be positive, seed nonnegative, max-attempts in 1..5")
    if args.seed + len(configurations) * args.samples - 1 > MAX_TRIAL_SEED:
        raise ValueError("Evaluation seed schedule exceeds the model seed range")
    model_record = None
    if args.provider == "ollama":
        policy = OllamaPolicy(args.model, base_url=args.base_url, temperature=args.temperature,
                              timeout=args.timeout, num_predict=args.num_predict)
        requested = args.model if ":" in args.model else args.model + ":latest"
        model_record = next((record for record in policy.list_models()
                             if record["name"] in (args.model, requested)), None)
        if model_record is None:
            raise ValueError("The selected model is not installed in local Ollama; no model was downloaded")
        policy.validate_local_model()
    else:
        policy = ScriptedRefundPolicy()
    evaluation = evaluate_policy(policy, configurations, samples=args.samples, seed=args.seed,
                                 max_calls=args.max_calls, max_attempts=args.max_attempts)
    artifacts = []
    receipts = []
    for sample in evaluation.samples:
        receipt = evaluation_sample_record(sample, root=output)
        receipts.append(receipt)
        if sample.episode is None:
            continue
        episode = sample.episode
        values = {
            receipt["trace"]: episode.trace,
            receipt["explanation"]: episode.explanation,
            receipt["evaluator_truth"]: {
                "scenario": sample.scenario, "seed": sample.seed,
                "config": to_dict(episode.config), "records": episode.ground_truth,
            },
        }
        for relative, value in values.items():
            path = output / relative
            _write_json(path, value)
            artifacts.append({"path": relative, "sha256": sha256(path.read_bytes()).hexdigest()})
    summary = evaluation.summary()
    _write_json(output / "results.json", {
        "package_version": __version__, "evaluation_kind": (
            "local_model" if args.provider == "ollama" else "scripted_smoke"
        ),
        "policy": evaluation.policy_metadata, "installed_model": model_record,
        "samples_per_case": args.samples, "initial_seed": args.seed,
        "max_attempts": args.max_attempts, "cases": [config.name for config in configurations],
        "summary": summary, "samples": receipts,
        "claim": "Adapter evaluation only; no attribution-method superiority or task generalization tested.",
    })
    _write_json(output / "trace-schema.json", get_trace_schema())
    _write_json(output / "manifest.json", {"package_version": __version__, "artifacts": artifacts})
    rows = []
    for receipt in receipts:
        rows.append("| " + " | ".join(str(receipt.get(key, "—")) for key in (
            "index", "scenario", "seed", "status", "policy_calls", "reported_assessment",
            "verified_outcome", "effect_origin", "assessment_alignment",
        )) + " |")
    report = (
        "# Policy evaluation\n\n"
        f"Provider: **{args.provider}**. Planned {summary['planned_samples']} samples; "
        f"completed {summary['completed_samples']}, failed {summary['failed_samples']}, "
        f"not started {summary['not_started_samples']}. "
        f"Policy calls: {summary['policy_calls']} / {summary['max_calls']}.\n\n"
        + ("This is an offline scripted-policy smoke evaluation. No language model was run.\n\n"
           if args.provider == "scripted" else
           "This evaluation calls a selected local Ollama model against simulated payments. "
           "It is a template-level smoke evaluation, not a held-out research study.\n\n")
        + "| Sample | Case | Seed | Status | Calls | Reported assessment | Verified outcome | Origin | Alignment |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows) + "\n\n"
        "Provider/protocol failures and unstarted samples are separate from consequence "
        "violations. Unknown readback remains unknown. Model seed settings are a "
        "reproducibility control, not a guarantee across models, servers, or hardware. "
        "Virtual payment deadlines exclude inference latency.\n\n"
        "The model receives declared task/context and public tool responses. Independent "
        "readback is revealed only after its final assessment. Evaluator labels and truth "
        "are in separate files and must not be passed to a policy or explainer. "
        "Manifest hashes check file integrity, not evidence authenticity.\n"
    )
    (output / "README.md").write_text(report, encoding="utf-8", newline="\n")
    print(f"Saved {summary['completed_samples']} completed and {summary['failed_samples']} failed "
          f"policy samples in {output.resolve()}")
    return 2 if evaluation.budget_exhausted or summary["failed_samples"] else 0


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
    evaluation = commands.add_parser("model-eval", help="Evaluate a bounded scripted or local model policy")
    evaluation.add_argument("--provider", choices=("scripted", "ollama"), default="scripted")
    evaluation.add_argument("--model")
    evaluation.add_argument("--base-url", default="http://127.0.0.1:11434")
    evaluation.add_argument("--temperature", type=float, default=0.2)
    evaluation.add_argument("--timeout", type=float, default=120)
    evaluation.add_argument("--num-predict", type=int, default=512)
    evaluation.add_argument("--samples", type=int, default=2)
    evaluation.add_argument("--seed", type=int, default=0)
    evaluation.add_argument("--max-calls", type=int, default=100)
    evaluation.add_argument("--max-attempts", type=int, default=2)
    evaluation.add_argument("--cases")
    evaluation.add_argument("--output", default="output/model-evaluation")
    evaluation.set_defaults(handler=_model_eval)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, TypeError, OSError, InsufficientEvidenceError) as error:
        print(f"consequa-x: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
