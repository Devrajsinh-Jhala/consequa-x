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


def _new_output(args, command):
    output = Path(args.output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"{command} requires a new or empty output directory to preserve each run")
    return output


def _prepare_policy(args):
    from .adapters.ollama import OllamaPolicy
    from .policies import ScriptedRefundPolicy

    if args.provider == "ollama" and not args.model:
        raise ValueError("--model is required with --provider ollama")
    if args.provider == "scripted" and args.model:
        raise ValueError("--model requires --provider ollama; scripted is an offline fixture")
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
    return policy, model_record


def _model_eval(args):
    from .benchmark.evaluation import evaluate_policy, evaluation_sample_record
    from .benchmark.policy_runner import MAX_TRIAL_SEED

    output = _new_output(args, "model-eval")
    configurations = demo_scenarios()
    if args.cases:
        names = args.cases.split(",")
        by_name = {config.name: config for config in configurations}
        if any(name not in by_name for name in names) or len(set(names)) != len(names):
            raise ValueError("cases must be unique known demo names, separated by commas")
        configurations = tuple(by_name[name] for name in names)
    # Validate the schedule before contacting a provider or writing artifacts.
    if args.samples < 1 or args.seed < 0 or args.max_calls < 1 or not 1 <= args.max_attempts <= 5:
        raise ValueError("samples/max-calls must be positive, seed nonnegative, max-attempts in 1..5")
    if args.seed + len(configurations) * args.samples - 1 > MAX_TRIAL_SEED:
        raise ValueError("Evaluation seed schedule exceeds the model seed range")
    policy, model_record = _prepare_policy(args)
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


def _model_experiment(args):
    from .benchmark.policy_experiment import branch_record, experiment_policy
    from .benchmark.policy_runner import MAX_TRIAL_SEED

    output = _new_output(args, "model-experiment")
    config = next(config for config in demo_scenarios() if config.name == args.case)
    names = args.candidates.split(",")
    if any(name not in RefundContext.__dataclass_fields__ for name in names) or len(set(names)) != len(names):
        raise ValueError("candidates must be unique declared context names, separated by commas")
    if args.samples < 2 or args.seed < 0 or args.max_calls < 1 or not 1 <= args.max_attempts <= 5:
        raise ValueError("samples must be at least 2, max-calls positive, seed nonnegative, max-attempts in 1..5")
    if args.seed + args.samples - 1 > MAX_TRIAL_SEED:
        raise ValueError("Paired seed schedule exceeds the model seed range")
    candidates = tuple(Intervention(name) for name in names)
    policy, model_record = _prepare_policy(args)
    experiment = experiment_policy(policy, config, candidates, samples=args.samples, seed=args.seed,
                                   max_calls=args.max_calls, max_attempts=args.max_attempts)
    artifacts = []
    receipts = []

    def save(relative, value):
        path = output / relative
        _write_json(path, value)
        artifacts.append({"path": relative, "sha256": sha256(path.read_bytes()).hexdigest()})

    by_candidate = {item.event_id: item for item in experiment.interventions}
    for branch in experiment.branches:
        receipt = branch_record(branch, root=output)
        receipts.append(receipt)
        if branch.episode is None:
            continue
        episode = branch.episode
        save(receipt["trace"], episode.trace)
        save(receipt["explanation"], episode.explanation)
        save(receipt["evaluator_truth"], {
            "scenario": config.name, "seed": branch.seed, "branch_index": branch.index,
            "intervention": to_dict(by_candidate.get(branch.candidate_id)),
            "config": to_dict(episode.config), "records": episode.ground_truth,
        })
    estimates = tuple(item.estimate for item in experiment.results if item.estimate is not None)
    factual = next((branch for branch in experiment.branches
                    if branch.candidate_id is None and branch.episode is not None), None)
    attribution_path = None
    attribution_trace = None
    if factual is not None and estimates:
        attribution_path = "attribution-explanation.json"
        attribution_trace = branch_record(factual, root=output)["trace"]
        save(attribution_path, explain(factual.episode.trace, estimates))
    summary = experiment.summary()
    save("results.json", {
        "package_version": __version__, "evaluation_kind": (
            "local_model_replay" if args.provider == "ollama" else "scripted_replay"
        ),
        "policy": experiment.policy_metadata, "installed_model": model_record,
        "scenario": config.name, "samples_per_condition": experiment.samples_per_condition,
        "initial_seed": args.seed, "seeds": experiment.seeds, "max_attempts": experiment.max_attempts,
        "interventions": experiment.interventions, "replay_mode": "isolated_simulation",
        "branch_order": "factual seeds, then each candidate's seeds in declaration order",
        "summary": summary, "branches": receipts, "estimates": experiment.results,
        "attribution_trace": attribution_trace, "attribution_explanation": attribution_path,
        "claim": "Single-template integration experiment; no method superiority or task generalization tested.",
    })
    save("trace-schema.json", get_trace_schema())
    rows = []
    for item in experiment.results:
        values = [item.event_id, item.target, item.status]
        if item.estimate is None:
            values += ["—", "—", "—", "—"]
        else:
            estimate = item.estimate
            lower, upper = estimate.confidence_interval
            values += [f"{estimate.baseline_rate:.3f}", f"{estimate.intervention_rate:.3f}",
                       f"{estimate.effect:+.3f}", f"[{lower:+.3f}, {upper:+.3f}]"]
        values += [str(value) for value in (
            item.known_pairs, item.unknown_pairs, item.failed_pairs, item.unstarted_pairs,
        )]
        rows.append("| " + " | ".join(values) + " |")
    report = (
        "# Paired policy replay\n\n"
        f"Provider: **{args.provider}**; case: **{config.name}**. "
        f"{experiment.samples_per_condition} paired seeds per condition. "
        f"Completed {summary['completed_branches']} of {summary['planned_branches']} branches; "
        f"failed {summary['failed_branches']}, not started {summary['not_started_branches']}. "
        f"Policy calls: {summary['policy_calls']} / {summary['max_calls']}.\n\n"
        + ("This is a scripted integration fixture. No language model was run.\n\n"
           if args.provider == "scripted" else
           "This calls a selected local Ollama model against simulated payments. "
           "A single-template replay does not establish generalization.\n\n")
        + "Each factual seed runs once and is reused across candidates and both targets. "
        "Each changed branch starts a fresh simulated world under the same fixed contract. "
        "Estimates read the collected episodes and make no additional policy calls.\n\n"
        "| Context | Target | Status | Original rate | Changed rate | Signed effect | Approx. 95% interval | Known pairs | Unknown | Failed | Unstarted |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows) + "\n\n"
        "Effects are original minus changed target probability, not responsibility shares. "
        "The consequence target is verified state satisfaction; another actor can satisfy "
        "that state. Each approximate conservative Wilson-difference interval applies to "
        "one estimate, without simultaneous coverage across candidates.\n\n"
        "A target estimate requires every planned pair to be usable. Unknown consequence "
        "pairs, provider/protocol failures, and unstarted pairs are recorded separately; "
        "none are dropped, redrawn, or assigned a fabricated outcome. Known action selection "
        "can still be estimated when consequence readback is unknown.\n\n"
        "Model phase seeds are a pairing control, not a guarantee of deterministic "
        "generation. Simulation deadlines exclude inference latency. "
        "The optional attribution explanation attaches only available estimates to a "
        "representative factual trace; its influence edges describe the replay distribution.\n\n"
        "Keep evaluator truth and run-level labels out of policy and explainer inputs. "
        "The manifest covers branch artifacts, estimates, schema, report, and any attribution "
        "explanation. Hashes detect changed files, not evidence authenticity. "
        "Actual model measurements, held-out tasks, and matched strong baselines remain "
        "necessary for the research paper.\n"
    )
    report_path = output / "README.md"
    report_path.write_text(report, encoding="utf-8", newline="\n")
    artifacts.append({"path": "README.md", "sha256": sha256(report_path.read_bytes()).hexdigest()})
    _write_json(output / "manifest.json", {"package_version": __version__, "artifacts": artifacts})
    print(f"Saved {summary['completed_branches']} completed and {summary['failed_branches']} failed "
          f"replay branches in {output.resolve()}")
    return 2 if experiment.budget_exhausted or summary["failed_branches"] else 0


def _add_policy_arguments(parser, *, samples, max_calls):
    parser.add_argument("--provider", choices=("scripted", "ollama"), default="scripted")
    parser.add_argument("--model")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--num-predict", type=int, default=512)
    parser.add_argument("--samples", type=int, default=samples)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-calls", type=int, default=max_calls)
    parser.add_argument("--max-attempts", type=int, default=2)


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
    _add_policy_arguments(evaluation, samples=2, max_calls=100)
    evaluation.add_argument("--cases")
    evaluation.add_argument("--output", default="output/model-evaluation")
    evaluation.set_defaults(handler=_model_eval)
    replay = commands.add_parser("model-experiment", help="Run bounded paired policy context replays")
    _add_policy_arguments(replay, samples=20, max_calls=400)
    replay.add_argument("--case", choices=tuple(config.name for config in demo_scenarios()), default="unsafe_retry")
    replay.add_argument("--candidates", default="vip_policy,vip_memory,retry_instruction,distractor")
    replay.add_argument("--output", default="output/model-experiment")
    replay.set_defaults(handler=_model_experiment)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, TypeError, OSError, InsufficientEvidenceError) as error:
        print(f"consequa-x: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
