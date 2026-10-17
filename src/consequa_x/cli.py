"""Trace explanation, offline replay, and bounded policy evaluations."""

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

from . import __version__
from .attribution import InsufficientEvidenceError, Intervention, leave_one_out
from .benchmark.runner import (
    RefundContext, RefundReplayRunner, ScenarioConfig, demo_scenarios, run_scenario,
)
from .explanation import explain
from .models import Trace, to_dict
from .report import render_report
from .schema import get_trace_schema


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def _demo(args):
    output = _new_output(args, "demo")
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
    output = _new_output(args, "experiment")
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
    source = Path(args.trace)
    output = Path(args.output) if args.output else None
    if output is not None:
        if output.resolve() == source.resolve():
            raise ValueError("Explanation output must differ from the source trace")
        if output.exists():
            raise ValueError("Explanation output must be a new file to preserve existing evidence")
    trace = Trace.from_json(source.read_text(encoding="utf-8"))
    result = explain(trace)
    if args.output:
        _write_json(output, result)
        print(f"Saved explanation to {Path(args.output).resolve()}")
    else:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, allow_nan=False))
    return 0


def _new_output(args, command):
    output = Path(args.output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"{command} requires a new or empty output directory to preserve each run")
    return output


def _report(args):
    source, output = Path(args.trace), Path(args.output)
    if output.resolve() == source.resolve():
        raise ValueError("Report output must differ from the source trace")
    if output.exists() or output.is_symlink():
        raise ValueError("Report output must be a new file to preserve existing evidence")
    try:
        trace = Trace.from_json(source.read_text(encoding="utf-8"))
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Cannot report an invalid schema-0.1 trace") from None
    document = render_report(trace, include_details=args.include_details)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against another process creating the file
    # between the preservation check and this write.
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(document)
    print(f"Saved offline report to {output.resolve()}")
    if args.include_details:
        print("Captured details are included. Review the report before sharing.")
    return 0


def _assessment_report(summary):
    metrics = summary["assessment_metrics"]

    def rate(name):
        item = metrics[name]
        value = "not available" if item["value"] is None else f"{100 * item['value']:.1f}%"
        return f"{value} ({item['numerator']}/{item['denominator']})"

    counts = metrics["reported_assessment"]
    return (
        "Reported assessments: " + ", ".join(f"{name} {count}" for name, count in counts.items())
        + ".\n\n"
        f"Definite claim coverage: {rate('claim_coverage')}; "
        f"assessable claim coverage: {rate('assessable_claim_coverage')}; "
        f"contradictions among assessable claims: {rate('contradiction_rate')}. "
        "Unknown assessments are abstentions; partial assessments remain separate. "
        "These counts score the structured status only; an unknown status can coexist "
        "with definite claims in the rationale, which requires separate review. "
        "These are hindsight comparisons with supported action-linked state, not a "
        "grade of what an ambiguous public response lets the policy know. Failed and "
        "unstarted runs have no final assessment and remain outside these denominators.\n\n"
    )


def _prepare_policy(args):
    from .adapters.ollama import OllamaPolicy, PROMPT_VERSION
    from .policies import ScriptedRefundPolicy

    if args.provider == "ollama" and not args.model:
        raise ValueError("--model is required with --provider ollama")
    if args.provider == "scripted" and args.model:
        raise ValueError("--model requires --provider ollama; scripted is an offline fixture")
    if args.provider == "scripted" and args.prompt_version is not None:
        raise ValueError("--prompt-version requires --provider ollama; scripted has no model prompt")
    model_record = None
    if args.provider == "ollama":
        policy = OllamaPolicy(args.model, base_url=args.base_url, temperature=args.temperature,
                              timeout=args.timeout, num_predict=args.num_predict,
                              prompt_version=args.prompt_version or PROMPT_VERSION)
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
    from .benchmark.study import STUDY_SCHEMA_VERSION, study_plan_from_json, template_wording_sha256

    output = _new_output(args, "model-eval")
    configurations = demo_scenarios()
    template_map = None
    study_plan = None
    study_metadata = None
    selected = ()
    if args.study:
        if args.cases or args.split is None:
            raise ValueError("--study requires --split and cannot be combined with --cases")
        study_bytes = Path(args.study).read_bytes()
        study_text = study_bytes.decode("utf-8")
        study_plan = study_plan_from_json(study_text)
        order_seed = args.seed if args.order_seed is None else args.order_seed
        selected = study_plan.select(args.split, order_seed=order_seed)
        configurations = tuple(case.config for case in selected)
        template_map = {case.case_id: case.template for case in selected}
        study_metadata = {
            "schema_version": STUDY_SCHEMA_VERSION, "study_id": study_plan.study_id,
            "manifest_sha256": sha256(study_bytes).hexdigest(),
            "split": args.split, "order_seed": order_seed,
            "case_order": [case.case_id for case in selected],
            "split_scope": "Declared template-family split, not a certification of prior exposure or held-out fault compositions.",
        }
    elif args.split is not None or args.order_seed is not None:
        raise ValueError("--split and --order-seed require --study")
    elif args.cases:
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
    if study_metadata is not None:
        study_metadata["planned_schedule"] = [
            {"index": index, "case_id": case.case_id, "template_id": case.template.template_id,
             "family_id": case.template.family_id, "seed": args.seed + index,
             "wording_sha256": template_wording_sha256(case.template)}
            for index, case in enumerate(case for case in selected for _ in range(args.samples))
        ]
    policy, model_record = _prepare_policy(args)
    evaluation = evaluate_policy(policy, configurations, samples=args.samples, seed=args.seed,
                                 max_calls=args.max_calls, max_attempts=args.max_attempts,
                                 templates=template_map)
    artifacts = []
    receipts = []
    by_case = {case.case_id: case for case in selected}
    for sample in evaluation.samples:
        receipt = evaluation_sample_record(sample, root=output)
        if study_plan is not None:
            case = by_case[sample.scenario]
            receipt.update(case_id=case.case_id, split=case.split,
                           template_id=case.template.template_id, family_id=case.template.family_id,
                           wording_sha256=template_wording_sha256(case.template))
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
    if study_plan is not None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "study-plan.json").write_bytes(study_bytes)
        artifacts.append({"path": "study-plan.json",
                          "sha256": sha256((output / "study-plan.json").read_bytes()).hexdigest()})
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
        **({"study": study_metadata} if study_metadata is not None else {}),
    })
    _write_json(output / "trace-schema.json", get_trace_schema())
    rows = []
    for receipt in receipts:
        rows.append("| " + " | ".join(str(receipt.get(key, "—")) for key in (
            "index", "scenario", "seed", "status", "policy_calls", "reported_assessment",
            "verified_outcome", "effect_origin", "assessment_alignment",
            "action_linked_consequence_satisfied",
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
        + _assessment_report(summary)
        + (f"Study: **{study_plan.study_id}**; declared split: **{args.split}**; "
           f"case-order seed: {study_metadata['order_seed']}. Template families are confined "
           "to one split. This assignment does not certify unseen model inputs or held-out "
           "fault compositions; final study scope still requires an exposure audit.\n\n"
           if study_plan is not None else "")
        + "| Sample | Case | Seed | Status | Calls | Reported assessment | Verified outcome | Origin | Alignment | Linked contract satisfied |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows) + "\n\n"
        "Provider/protocol failures and unstarted samples are separate from consequence "
        "violations. Unknown readback remains unknown. Model seed settings are a "
        "reproducibility control, not a guarantee across models, servers, or hardware. "
        "Virtual payment deadlines exclude inference latency.\n\n"
        "The linked-contract target requires qualifying action-linked refund witnesses "
        "as well as satisfied state; another actor's refund is not agent success. "
        "Missing provenance leaves this target unknown.\n\n"
        "The model receives declared task/context and public tool responses. Independent "
        "readback is revealed only after its final assessment. Evaluator labels and truth "
        "are in separate files and must not be passed to a policy or explainer. "
        "Manifest hashes check file integrity, not evidence authenticity.\n"
    )
    (output / "README.md").write_text(report, encoding="utf-8", newline="\n")
    for relative in ("results.json", "trace-schema.json", "README.md"):
        artifacts.append({"path": relative, "sha256": sha256((output / relative).read_bytes()).hexdigest()})
    _write_json(output / "manifest.json", {"package_version": __version__, "artifacts": artifacts})
    print(f"Saved {summary['completed_samples']} completed and {summary['failed_samples']} failed "
          f"policy samples in {output.resolve()}")
    return 2 if evaluation.budget_exhausted or summary["failed_samples"] else 0


def _model_experiment(args):
    from .benchmark.policy_experiment import branch_record, experiment_policy
    from .benchmark.policy_runner import MAX_TRIAL_SEED
    from .attribution import REPLAY_TARGETS
    from .benchmark.templates import REFUND_TASK_TEMPLATES

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
    targets = tuple(args.targets.split(","))
    if not targets or len(set(targets)) != len(targets) or any(
        target not in REPLAY_TARGETS for target in targets
    ):
        raise ValueError("targets must be unique supported replay target names, separated by commas")
    template = REFUND_TASK_TEMPLATES[args.template]
    policy, model_record = _prepare_policy(args)
    experiment = experiment_policy(policy, config, candidates, samples=args.samples, seed=args.seed,
                                   max_calls=args.max_calls, max_attempts=args.max_attempts,
                                   targets=targets, template=template)
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
        "targets": experiment.targets, "template": experiment.template.to_dict(),
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
        + _assessment_report(summary)
        + "Each factual seed runs once and is reused across candidates and all selected targets. "
        "Each changed branch starts a fresh simulated world under the same fixed contract. "
        "Estimates read the collected episodes and make no additional policy calls.\n\n"
        "| Context | Target | Status | Original rate | Changed rate | Signed effect | Approx. 95% interval | Known pairs | Unknown | Failed | Unstarted |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows) + "\n\n"
        "Effects are original minus changed target probability, not responsibility shares. "
        "The consequence target is verified state satisfaction; another actor can satisfy "
        "that state. Each approximate conservative Wilson-difference interval applies to "
        "one estimate, without simultaneous coverage across candidates.\n\n"
        "The optional action_linked_consequence target additionally requires qualifying "
        "action-linked witnesses; satisfied state with exclusively external origin is "
        "false, and insufficient provenance is unknown. This is a supported-evidence "
        "target, not causal responsibility.\n\n"
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
    from .adapters.ollama import PROMPT_PROFILES

    parser.add_argument("--provider", choices=("scripted", "ollama"), default="scripted")
    parser.add_argument("--model")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--num-predict", type=int, default=512)
    parser.add_argument("--prompt-version", choices=tuple(PROMPT_PROFILES),
                        help="Ollama prompt profile; defaults to refund-policy-v1")
    parser.add_argument("--samples", type=int, default=samples)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-calls", type=int, default=max_calls)
    parser.add_argument("--max-attempts", type=int, default=2)


def _decision_experiment(args):
    """Export bounded decision continuations separately from context effects."""
    from copy import deepcopy

    from .attribution import REPLAY_TARGETS
    from .benchmark.decision_contrastive import contrastive_decisions
    from .benchmark.evaluation import BudgetedPolicy, CallBudgetExceeded
    from .benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
    from .benchmark.targets import episode_outcome
    from .benchmark.templates import REFUND_TASK_TEMPLATES
    from .policies import PolicyError, validate_reply

    output = _new_output(args, "decision-experiment")
    if args.samples < 2 or args.max_calls < 1 or not 1 <= args.max_attempts <= 5:
        raise ValueError("samples must be at least 2, max-calls positive, max-attempts in 1..5")
    if not 0 <= args.factual_seed <= MAX_TRIAL_SEED:
        raise ValueError("factual-seed exceeds the model seed range")
    # Preflight the longest possible factual capture before contacting a provider.
    if args.seed < 0 or args.seed + (args.max_attempts + 1) * args.samples - 1 > MAX_TRIAL_SEED:
        raise ValueError("Conservative continuation seed schedule exceeds the model seed range")
    if args.seed <= args.factual_seed <= args.seed + (args.max_attempts + 1) * args.samples - 1:
        raise ValueError("Conservative continuation seed schedule overlaps the factual seed")
    if not math.isfinite(args.confidence) or not 0 < args.confidence < 1:
        raise ValueError("confidence must be a finite number strictly between 0 and 1")
    if args.bootstrap_samples < 2 or args.bootstrap_seed < 0:
        raise ValueError("bootstrap-samples must be at least 2 and bootstrap-seed nonnegative")
    targets = tuple(args.targets.split(","))
    if not targets or len(set(targets)) != len(targets) or any(
        target not in REPLAY_TARGETS for target in targets
    ):
        raise ValueError("targets must be unique supported replay target names, separated by commas")
    config = next(config for config in demo_scenarios() if config.name == args.case)
    template = REFUND_TASK_TEMPLATES[args.template]
    policy, model_record = _prepare_policy(args)
    bounded = BudgetedPolicy(policy, args.max_calls)

    class FactualRecorder:
        def __init__(self):
            self.decisions = []

        @property
        def metadata(self):
            return bounded.metadata

        def decide(self, request, *, seed):
            receipt = {"index": len(self.decisions), "stage": request.stage,
                       "model_seed": seed, "request": to_dict(request), "reply": None}
            before = bounded.calls
            try:
                reply = bounded.decide(deepcopy(request), seed=seed)
                validate_reply(request, reply)
                receipt["reply"] = to_dict(reply)
                return reply
            except PolicyError as error:
                receipt.update(error_type=type(error).__name__, error=str(error))
                raise
            finally:
                receipt["policy_calls"] = bounded.calls - before
                self.decisions.append(receipt)

    recorder = FactualRecorder()
    factual = None
    factual_error = None
    try:
        factual = run_policy_scenario(config, recorder, seed=args.factual_seed,
                                      max_attempts=args.max_attempts, template=template)
    except PolicyError as error:
        factual_error = error
    factual_calls = bounded.calls
    experiment = None
    estimator_error = None
    if factual is not None:
        try:
            experiment = contrastive_decisions(
                factual, bounded, samples=args.samples, seed=args.seed, targets=targets,
                template=template, confidence=args.confidence,
                bootstrap_samples=args.bootstrap_samples, bootstrap_seed=args.bootstrap_seed,
                interval_method=args.interval_method,
            )
        except (ValueError, TypeError) as error:
            # A complete recorded factual episode may fail replay identity or
            # capture validation. Preserve its evidence without making a draw.
            if bounded.calls != factual_calls:
                raise
            estimator_error = error
    artifacts = []

    def save(relative, value):
        path = output / relative
        _write_json(path, value)
        artifacts.append({"path": relative, "sha256": sha256(path.read_bytes()).hexdigest()})

    def save_episode(episode, stem, extra_truth):
        paths = {"trace": f"traces/{stem}.json", "explanation": f"explanations/{stem}.json",
                 "evaluator_truth": f"evaluator_truth/{stem}.json"}
        save(paths["trace"], episode.trace)
        save(paths["explanation"], episode.explanation)
        save(paths["evaluator_truth"], {
            "scenario": config.name, "seed": episode.seed, "config": to_dict(episode.config),
            "records": episode.ground_truth, **extra_truth,
        })
        return paths

    factual_receipt = {
        "status": "completed" if factual is not None else "failed", "seed": args.factual_seed,
        "policy_calls": factual_calls, "decisions": recorder.decisions,
    }
    if factual is None:
        factual_receipt.update(error_type=type(factual_error).__name__, error=str(factual_error))
    else:
        factual_receipt.update(save_episode(factual, "factual", {"role": "factual"}))
        factual_receipt["trace_sha256"] = sha256(
            (output / factual_receipt["trace"]).read_bytes()
        ).hexdigest()
        factual_receipt["outcome"] = to_dict(episode_outcome(factual))
    receipts = []
    planned_schedule = []
    if experiment is not None:
        by_branch = {(branch.decision_index, branch.continuation_seed): branch
                     for branch in experiment.branches}
        for decision_index, seeds in enumerate(experiment.planned_seeds):
            for continuation_seed in seeds:
                planned_schedule.append({"index": len(planned_schedule),
                                         "decision_index": decision_index,
                                         "continuation_seed": continuation_seed,
                                         "hold_count": decision_index})
        for planned in planned_schedule:
            branch = by_branch.get((planned["decision_index"], planned["continuation_seed"]))
            replay = branch.replay if branch is not None else None
            receipt = dict(planned)
            if replay is None:
                receipt.update(status="not_started", policy_calls=0, decisions=[],
                               reason="Shared policy-call budget exhausted before this branch")
            else:
                receipt.update(replay.summary(), decisions=to_dict(replay.decisions))
                if replay.episode is not None:
                    receipt.update(save_episode(replay.episode, f"branch_{branch.index:05d}", {
                        "role": "continuation", "branch_index": branch.index,
                        "decision_index": branch.decision_index,
                        "continuation_seed": branch.continuation_seed,
                        "hold_count": replay.hold_count,
                    }))
                    receipt["outcome"] = to_dict(episode_outcome(replay.episode))
            receipts.append(receipt)
    completed = sum(receipt["status"] == "completed" for receipt in receipts)
    failed = sum(receipt["status"] == "failed" for receipt in receipts)
    not_started = sum(receipt["status"] == "not_started" for receipt in receipts)
    continuation_calls = bounded.calls - factual_calls
    exhausted = (isinstance(factual_error, CallBudgetExceeded)
                 or (experiment is not None and experiment.budget_exhausted))
    settings = {
        "scenario": config.name, "template": template.to_dict(), "targets": targets,
        "factual_seed": args.factual_seed, "initial_continuation_seed": args.seed,
        "samples_per_decision": args.samples, "max_attempts": args.max_attempts,
        "confidence": args.confidence, "bootstrap_samples": args.bootstrap_samples,
        "bootstrap_seed": args.bootstrap_seed,
        "interval_method": args.interval_method,
        "seed_preflight": "seed + (max_attempts + 1) * samples - 1 <= MAX_TRIAL_SEED",
    }
    availability = {
        "status": "available" if experiment is not None else
                  "refused" if estimator_error is not None else "unavailable",
        "reason": None if experiment is not None else
                  "Completed factual capture failed estimator preflight; no continuations were drawn"
                  if estimator_error is not None else "Factual capture failed; no estimator was run",
        "error_type": type(estimator_error).__name__ if estimator_error is not None else None,
        "error": str(estimator_error) if estimator_error is not None else None,
    }
    planning = {
        "source": "validated_capture" if experiment is not None else
                  "unvalidated_capture" if factual is not None else "incomplete_capture",
        "recorded_factual_decisions": len(recorder.decisions),
        "conservative_max_positions": args.max_attempts + 1,
        "conservative_max_branches": (args.max_attempts + 1) * args.samples,
        "conservative_seed_range": [args.seed, args.seed + (args.max_attempts + 1) * args.samples - 1],
        "scope": "Conservative preflight bounds; a decision-specific schedule exists only after factual validation",
    }
    save("results.json", {
        "package_version": __version__, "evaluation_kind": (
            "local_model_decision_replay" if args.provider == "ollama"
            else "scripted_decision_replay"
        ),
        "status": "available" if experiment is not None else "unavailable",
        "reason": availability["reason"], "estimator_availability": availability,
        "planning": planning,
        "policy": bounded.metadata, "installed_model": model_record, "settings": settings,
        "factual": factual_receipt, "branches": receipts,
        "planned_seeds": experiment.planned_seeds if experiment is not None else None,
        "planned_schedule": planned_schedule if experiment is not None else None,
        "planned_branches": experiment.planned_branches if experiment is not None else None,
        "branch_order": "factual decision index, then continuation seeds in declaration order",
        "summary": experiment.summary() if experiment is not None else None,
        "method": experiment.method_record() if experiment is not None else None,
        "estimates": [item.to_dict() for item in experiment.results] if experiment is not None else [],
        "loci": experiment.loci if experiment is not None else [],
        "calls": {"total": bounded.calls, "factual": factual_calls,
                  "continuation": continuation_calls, "max_calls": args.max_calls,
                  "budget_exhausted": exhausted},
        "signed_effect": "changed bad-outcome probability minus observed factual bad-outcome indicator",
        "claim": "Binary decision-resampling adaptation; no Shapley allocation, method superiority, or task generalization tested.",
    })
    save("trace-schema.json", get_trace_schema())
    rows = []
    if experiment is not None:
        for item in experiment.results:
            interval = ("—" if item.confidence_interval is None else
                        f"[{item.confidence_interval[0]:+.3f}, {item.confidence_interval[1]:+.3f}]")
            changed = "—" if item.changed_bad_rate is None else f"{item.changed_bad_rate:.3f}"
            effect = "—" if item.effect is None else f"{item.effect:+.3f}"
            rows.append("| " + " | ".join(str(value) for value in (
                item.decision_index, item.event_id, item.target, item.status, item.factual_bad,
                changed, effect, interval, item.known_samples, item.unknown_samples,
                item.failed_samples, item.unstarted_samples, item.significant_rescue,
            )) + " |")
    report = (
        "# Decision contrastive experiment\n\n"
        f"Provider: **{args.provider}**; case: **{config.name}**. "
        f"One factual capture; {args.samples} planned continuations per reached factual decision. "
        f"Continuation branches: {completed} completed, {failed} failed, {not_started} not started. "
        f"Shared policy-call budget: {bounded.calls} / {args.max_calls} "
        f"({factual_calls} factual, {continuation_calls} continuation calls).\n\n"
        + ("This is a scripted integration fixture. No language model was run.\n\n"
           if args.provider == "scripted" else
           "This calls a selected local Ollama model against simulated payments. "
           "A single observed factual trajectory does not establish task generalization.\n\n")
        + ("The factual capture failed. Its reached requests and errors are recorded; "
           "there is no factual trace, estimator result, or invented outcome. The planned "
           "decision schedule is unavailable because no complete factual trace exists.\n\n"
           if factual is None else "")
        + ("The factual capture completed, but estimator preflight was refused. "
           "Its original trace, explanation, and evaluator record are preserved along "
           "with the typed validation error. No continuation was drawn or redrawn. "
           "Recorded position counts and conservative bounds are marked "
           "`unvalidated_capture`; no decision-specific schedule or estimate is invented.\n\n"
           if estimator_error is not None else "")
        + "Each changed branch resets the factual payment world, holds decisions before "
        "the tested index, and resamples that decision and its suffix with the same declared "
        "policy. All selected targets use the same collected branches. Held decisions cost "
        "no provider call; actual attempted fresh calls, including failures, consume the "
        "shared budget. Model phase seeds are reproducibility controls, not guarantees.\n\n"
        "| Decision | Event | Target | Status | Factual bad | Changed bad rate | Signed effect | Interval | Known | Unknown | Failed | Unstarted | Significant rescue |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows) + "\n\n"
        "Bad means the selected target is false; unknown target values remain unknown. "
        "Signed effects are changed bad-outcome probability minus the single observed "
        "factual bad-outcome indicator. Negative effects mean the changed distribution "
        "reduces bad outcomes. These are distinct from context neutralization effects and "
        "are not responsibility shares.\n\n"
        f"Interval method: `{args.interval_method}`, confidence {args.confidence:g}. "
        + (f"The percentile option uses {args.bootstrap_samples} pure-Python bootstrap resamples, "
           f"seed {args.bootstrap_seed}, and linear interpolation. "
           if args.interval_method == "percentile_bootstrap" else
           "The binomial interval for the changed bad probability is shifted by the "
           "constant observed factual label. Wilson is approximate; Clopper–Pearson "
           "is conservative under independent known binomial draws. ")
        +
        "Every planned continuation must be usable and at least two samples are required; "
        "unknowns, failures, and unstarted branches refuse the whole estimate. A locus is "
        "refused unless every tested decision for that target is usable. The latest "
        "decision with a negative point effect and strictly negative interval upper bound "
        "is a significant rescue. "
        "Intervals do not provide simultaneous coverage across decisions or targets.\n\n"
        "The factual baseline is one observed indicator, not a separately estimated "
        "rate. The percentile option resets its random seed at each position and can "
        "collapse for identical samples. The binomial options preserve uncertainty at "
        "homogeneous samples and pin probability boundaries to zero and one.\n\n"
        "A degenerate interval does not establish zero population variance or certain "
        "rescue. The nominal locus rule does not prove unique causation, and requested "
        "seeds do not establish independent samples or equal hidden model state.\n\n"
        "This independently written CAR-style binary adaptation adds contrastive "
        "decision localization; matched baseline comparison and domain interaction "
        "recovery remain research work. No attribution overlay is attached to these signed effects.\n\n"
        "`traces/` contains completed factual and branch evidence only. `explanations/` "
        "is independently derived from each trace, while `evaluator_truth/` contains "
        "simulator labels that must not enter the policy or explainer. `results.json` "
        "preserves every reached request/reply, failures, the complete planned continuation "
        "seed schedule, per-target coverage, and loci. `trace-schema.json` describes each "
        "trace. `manifest.json` covers every other exported file; hashes detect changed "
        "bytes and do not establish authenticity.\n"
    )
    report_path = output / "README.md"
    report_path.write_text(report, encoding="utf-8", newline="\n")
    artifacts.append({"path": "README.md", "sha256": sha256(report_path.read_bytes()).hexdigest()})
    _write_json(output / "manifest.json", {"package_version": __version__, "artifacts": artifacts})
    print(f"Saved decision experiment with {completed} completed, {failed} failed, and "
          f"{not_started} unstarted continuations in {output.resolve()}")
    return 2 if factual is None or estimator_error is not None or failed or exhausted else 0


def _decision_shapley(args):
    """Export fresh positional coalition walks and separate endpoint diagnostics."""
    from copy import deepcopy

    from .attribution import REPLAY_TARGETS
    from .benchmark.decision_shapley import shapley_decisions
    from .benchmark.evaluation import BudgetedPolicy, CallBudgetExceeded
    from .benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
    from .benchmark.targets import episode_outcome
    from .benchmark.templates import REFUND_TASK_TEMPLATES
    from .policies import PolicyError, validate_reply

    output = _new_output(args, "decision-shapley")
    if args.pairs < 2 or args.samples < 1 or args.endpoint_samples < 2:
        raise ValueError("pairs and endpoint-samples must be at least 2; samples must be positive")
    if args.max_calls < 1 or not 1 <= args.max_attempts <= 5:
        raise ValueError("max-calls must be positive and max-attempts in 1..5")
    if not 0 <= args.factual_seed <= MAX_TRIAL_SEED:
        raise ValueError("factual-seed exceeds the model seed range")
    if not 0 <= args.permutation_seed <= 2**31 - 1:
        raise ValueError("permutation-seed must be in 0..2147483647")
    planned_bound = 2 * args.endpoint_samples + 2 * args.pairs * (args.max_attempts + 2) * args.samples
    if args.seed < 0 or args.seed + planned_bound - 1 > MAX_TRIAL_SEED:
        raise ValueError("Conservative coalition seed schedule exceeds the model seed range")
    if args.seed <= args.factual_seed <= args.seed + planned_bound - 1:
        raise ValueError("Conservative coalition seed schedule overlaps the factual seed")
    if not math.isfinite(args.confidence) or not 0 < args.confidence < 1:
        raise ValueError("confidence must be finite and strictly between 0 and 1")
    targets = tuple(args.targets.split(","))
    if not targets or len(set(targets)) != len(targets) or any(
        target not in REPLAY_TARGETS for target in targets
    ):
        raise ValueError("targets must be unique supported replay target names, separated by commas")
    config = next(config for config in demo_scenarios() if config.name == args.case)
    template = REFUND_TASK_TEMPLATES[args.template]
    policy, model_record = _prepare_policy(args)
    bounded = BudgetedPolicy(policy, args.max_calls)

    class FactualRecorder:
        def __init__(self):
            self.decisions = []

        @property
        def metadata(self):
            return bounded.metadata

        def decide(self, request, *, seed):
            receipt = {"index": len(self.decisions), "stage": request.stage,
                       "model_seed": seed, "request": to_dict(request), "reply": None}
            before = bounded.calls
            try:
                reply = bounded.decide(deepcopy(request), seed=seed)
                validate_reply(request, reply)
                receipt["reply"] = to_dict(reply)
                return reply
            except (PolicyError, ValueError, TypeError) as error:
                receipt.update(error_type=type(error).__name__, error=str(error))
                raise
            finally:
                receipt["policy_calls"] = bounded.calls - before
                self.decisions.append(receipt)

    recorder = FactualRecorder()
    factual = experiment = factual_error = estimator_error = None
    try:
        factual = run_policy_scenario(config, recorder, seed=args.factual_seed,
                                      max_attempts=args.max_attempts, template=template)
    except (PolicyError, ValueError, TypeError) as error:
        factual_error = error
    factual_calls = bounded.calls
    if factual is not None:
        try:
            experiment = shapley_decisions(
                factual, bounded, pairs=args.pairs, samples_per_eval=args.samples,
                endpoint_samples=args.endpoint_samples, seed=args.seed,
                permutation_seed=args.permutation_seed, confidence=args.confidence,
                targets=targets, template=template,
                interval_method=args.interval_method,
                endpoint_interval_method=args.endpoint_interval_method,
                coalition_game=args.coalition_game,
            )
        except (PolicyError, ValueError, TypeError) as error:
            if bounded.calls != factual_calls:
                raise
            estimator_error = error
    artifacts = []

    def save(relative, value):
        path = output / relative
        _write_json(path, value)
        artifacts.append({"path": relative, "sha256": sha256(path.read_bytes()).hexdigest()})

    def save_episode(episode, stem, extra_truth):
        paths = {"trace": f"traces/{stem}.json", "explanation": f"explanations/{stem}.json",
                 "evaluator_truth": f"evaluator_truth/{stem}.json"}
        save(paths["trace"], episode.trace)
        save(paths["explanation"], episode.explanation)
        save(paths["evaluator_truth"], {"scenario": config.name, "seed": episode.seed,
                                      "config": to_dict(episode.config),
                                      "records": episode.ground_truth, **extra_truth})
        return paths

    factual_receipt = {"status": "completed" if factual is not None else "failed",
                       "seed": args.factual_seed, "policy_calls": factual_calls,
                       "decisions": recorder.decisions}
    if factual is None:
        factual_receipt.update(error_type=type(factual_error).__name__, error=str(factual_error))
    else:
        factual_receipt.update(save_episode(factual, "factual", {"role": "factual"}))
        factual_receipt["trace_sha256"] = sha256(
            (output / factual_receipt["trace"]).read_bytes()
        ).hexdigest()
        factual_receipt["outcome"] = to_dict(episode_outcome(factual))
    schedule = to_dict(experiment.slots) if experiment is not None else None
    receipts = []
    if experiment is not None:
        by_index = {branch.slot.index: branch for branch in experiment.branches}
        for slot in experiment.slots:
            receipt = to_dict(slot)
            branch = by_index.get(slot.index)
            if branch is None:
                receipt.update(status="not_started", policy_calls=0, decisions=[],
                               reason="Shared policy-call budget blocked an earlier planned branch")
            else:
                replay = branch.replay
                receipt.update(replay.summary(), decisions=to_dict(replay.decisions))
                if replay.episode is not None:
                    receipt.update(save_episode(replay.episode, f"branch_{slot.index:05d}", {
                        "role": slot.role, "slot": to_dict(slot),
                    }))
                    receipt["outcome"] = to_dict(episode_outcome(replay.episode))
            receipts.append(receipt)
    counts = {status: sum(item["status"] == status for item in receipts)
              for status in ("completed", "invalid", "failed", "not_started")}
    exhausted = (isinstance(factual_error, CallBudgetExceeded)
                 or (experiment is not None and experiment.budget_exhausted))
    availability = {"status": "available" if experiment is not None else
                             "refused" if estimator_error is not None else "unavailable",
                    "reason": None if experiment is not None else
                              "Completed factual capture failed estimator preflight"
                              if estimator_error is not None else "Factual capture failed",
                    "error_type": type(estimator_error).__name__ if estimator_error else None,
                    "error": str(estimator_error) if estimator_error else None}
    save("results.json", {
        "package_version": __version__, "evaluation_kind": (
            "local_model_decision_shapley" if args.provider == "ollama"
            else "scripted_decision_shapley"),
        "estimator_availability": availability,
        "planning": {"source": "validated_capture" if experiment is not None else
                              "unvalidated_capture" if factual is not None else "incomplete_capture",
                     "recorded_factual_decisions": len(recorder.decisions),
                     "conservative_max_positions": args.max_attempts + 1,
                     "conservative_max_branches": planned_bound,
                     "conservative_seed_range": [args.seed, args.seed + planned_bound - 1]},
        "policy": bounded.metadata, "installed_model": model_record,
        "settings": {"scenario": config.name, "template": template.to_dict(), "targets": targets,
                     "factual_seed": args.factual_seed, "initial_continuation_seed": args.seed,
                     "pairs": args.pairs, "samples_per_eval": args.samples,
                     "endpoint_samples": args.endpoint_samples,
                     "permutation_seed": args.permutation_seed, "confidence": args.confidence,
                     "max_attempts": args.max_attempts, "coalition_game": args.coalition_game,
                     "interval_method": args.interval_method,
                     "endpoint_interval_method": args.endpoint_interval_method},
        "factual": factual_receipt, "planned_schedule": schedule, "branches": receipts,
        "permutations": experiment.permutations if experiment is not None else None,
        "summary": experiment.summary() if experiment is not None else None,
        "method": experiment.method_record() if experiment is not None else None,
        "estimates": [item.to_dict() for item in experiment.results] if experiment is not None else [],
        "endpoint_checks": experiment.endpoint_checks if experiment is not None else [],
        "calls": {"total": bounded.calls, "factual": factual_calls,
                  "continuation": bounded.calls - factual_calls, "max_calls": args.max_calls,
                  "budget_exhausted": exhausted},
        "signed_contribution": "held-factual coalition bad probability minus preceding coalition bad probability",
        "claim": "Conservative positional coalition adaptation; no interval calibration, model superiority, or task generalization established.",
    })
    save("trace-schema.json", get_trace_schema())
    rows = []
    if experiment is not None:
        for item in experiment.results:
            interval = "—" if item.confidence_interval is None else str(item.confidence_interval)
            rows.append(f"| {item.decision_index} | {item.target} | {item.status} | "
                        f"{item.shapley_value} | {interval} | {item.known_pairs} / {args.pairs} |")
    report = (
        "# Decision Shapley experiment\n\n"
        f"Provider: **{args.provider}**; case: **{config.name}**. "
        f"{args.pairs} planned antithetic pairs, {args.samples} draws per coalition evaluation. "
        f"Branches: {counts['completed']} completed, {counts['invalid']} invalid, "
        f"{counts['failed']} failed, {counts['not_started']} not started. "
        f"Actual calls: {bounded.calls} / {args.max_calls}, including {factual_calls} factual calls.\n\n"
        + ("Scripted integration example; no language model was run.\n\n"
           if args.provider == "scripted" else "Local model calls act only on simulated payments.\n\n")
        + ("Factual recording or estimator preflight was unavailable. Original completed "
           "evidence or reached failure receipts are retained; no coalition schedule, "
           "outcome, or estimate is fabricated.\n\n" if experiment is None else "")
        + "A coalition holds its recorded decisions at compatible positional stages and "
        f"resamples other decisions. Changed public inputs are allowed. Game: `{args.coalition_game}`. "
        + ("A requested held position that is not reached invalidates that branch. "
           if args.coalition_game == "strict" else
           "Normally unreached held positions are recorded as inactive; the completed "
           "trajectory supplies the actual outcome. Reached incompatible decisions stay invalid. ")
        + "Only completed valid branches have outcome labels. Every evaluation is fresh, including repeated "
        "coalitions. All requested targets reuse each branch without additional calls.\n\n"
        "| Decision | Target | Status | Signed contribution | Interval | Known pairs |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows) + "\n\n"
        "Positive contributions mean holding a factual decision increases bad-outcome "
        "probability; negative contributions mean it is protective. Values are not "
        "normalized responsibility shares. One averaged forward/reverse vector is one "
        f"observation. Pair interval: `{args.interval_method}`; endpoint interval: "
        f"`{args.endpoint_interval_method}`. Normal intervals use sample variance; "
        "Hoeffding uses the declared [-1,1] pair range and can be wide. Exact endpoint "
        "differences split the failure allowance across two binomial marginals. "
        "Their statements require the declared independent sampling assumptions. "
        "Incomplete target path coverage refuses its whole vector; unknown, "
        "invalid, failed, and unstarted draws remain separate, with no redraws.\n\n"
        "Independent empty/full endpoint samples lie outside the permutation walks. "
        "The discrepancy is coefficient sum minus that independently sampled endpoint "
        "difference, not a forced efficiency identity or a statistical pass/fail test. "
        "Endpoint refusal is separate from coefficient refusal.\n\n"
        "These conditional intervals have no multiplicity adjustment or calibrated "
        "coverage guarantee for live models. Homogeneous samples can collapse normal "
        "intervals; a small pair "
        "count and requested seeds do not establish certainty or independence. Strict "
        "unreachable-position refusal makes some variable-length refund games unavailable. "
        "A fixed-length mathematical interaction oracle is a different mechanism from "
        "this refund adapter. The implementation is independently written and declares "
        "its differences from the pinned CAR reference.\n\n"
        "Evaluator truth stays separate from policy/explainer inputs. Manifests detect "
        "changed bytes, not authenticity. No context-effect graph overlay is produced.\n"
    )
    report_path = output / "README.md"
    report_path.write_text(report, encoding="utf-8", newline="\n")
    artifacts.append({"path": "README.md", "sha256": sha256(report_path.read_bytes()).hexdigest()})
    _write_json(output / "manifest.json", {"package_version": __version__, "artifacts": artifacts})
    print(f"Saved Shapley experiment with {counts['completed']} completed, "
          f"{counts['invalid']} invalid, {counts['failed']} failed, "
          f"{counts['not_started']} unstarted branches in {output.resolve()}")
    return 2 if experiment is None or exhausted or counts["invalid"] or counts["failed"] else 0


def _calibrate_attribution(args):
    from .benchmark.calibration import CalibrationPlan
    from .benchmark.calibration_export import export_calibration

    settings = {"repeats": args.replicates, "samples": args.samples, "pairs": args.pairs,
                "samples_per_eval": args.samples_per_eval,
                "endpoint_samples": args.endpoint_samples,
                "bootstrap_samples": args.bootstrap_samples,
                "confidence": args.confidence, "seed": args.seed, "max_calls": args.max_calls}
    if args.mechanisms is not None:
        settings["mechanisms"] = tuple(args.mechanisms.split(","))
    export_calibration(CalibrationPlan(**settings), args.output, source_revision=args.source_revision)
    return 0


def _compare_intervals(args):
    from .benchmark.interval_comparison import comparison_plan, export_interval_comparison

    settings = {"repeats": args.replicates, "samples": args.samples, "pairs": args.pairs,
                "samples_per_eval": args.samples_per_eval, "endpoint_samples": args.endpoint_samples,
                "bootstrap_samples": args.bootstrap_samples, "confidence": args.confidence,
                "seed": args.seed, "max_calls": args.max_calls}
    export_interval_comparison(comparison_plan(**settings), args.output,
                               source_revision=args.source_revision, theory_only=args.theory_only)
    return 0


def _refund_interactions(args):
    from .benchmark.interaction_export import export_refund_interactions

    result = export_refund_interactions(args.output, source_revision=args.source_revision,
                                        seed=args.seed, mechanisms=args.mechanism)
    print(f"Saved refund interaction enumeration in {Path(args.output).resolve()}; "
          f"{result['actual_policy_calls']} actual synthetic policy calls")
    return 0


def _interaction_sampling(args):
    from .benchmark.interaction_sampling import InteractionSamplingPlan, export_interaction_sampling

    plan = InteractionSamplingPlan(repeats=args.repeats, pairs=args.pairs,
        samples_per_eval=args.samples, endpoint_samples=args.endpoint_samples,
        confidence=args.confidence, seed=args.seed, max_calls=args.max_calls)
    result = export_interaction_sampling(plan, args.output, source_revision=args.source_revision,
                                         workers=args.workers)
    print(f"Saved {result['retained_trials']} interaction trials in {Path(args.output).resolve()}")
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
    report = commands.add_parser("report", help="Create a self-contained offline HTML evidence report")
    report.add_argument("trace", help="Existing schema-0.1 trace JSON")
    report.add_argument("--output", required=True, help="New HTML file; existing files are preserved")
    report.add_argument("--include-details", action="store_true",
                        help="Include potentially sensitive captured values as inert escaped text")
    report.set_defaults(handler=_report)
    evaluation = commands.add_parser("model-eval", help="Evaluate a bounded scripted or local model policy")
    _add_policy_arguments(evaluation, samples=2, max_calls=100)
    evaluation.add_argument("--cases")
    evaluation.add_argument("--study", help="Evaluator-only refund-study-v1 JSON manifest")
    evaluation.add_argument("--split", choices=("tuning", "validation", "held_out"))
    evaluation.add_argument("--order-seed", type=int, help="Study case-order seed; defaults to --seed")
    evaluation.add_argument("--output", default="output/model-evaluation")
    evaluation.set_defaults(handler=_model_eval)
    replay = commands.add_parser("model-experiment", help="Run bounded paired policy context replays")
    _add_policy_arguments(replay, samples=20, max_calls=400)
    replay.add_argument("--case", choices=tuple(config.name for config in demo_scenarios()), default="unsafe_retry")
    replay.add_argument("--candidates", default="vip_policy,vip_memory,retry_instruction,distractor")
    replay.add_argument("--targets", default="action,consequence",
                        help="Comma-separated action, consequence, action_linked_consequence")
    from .benchmark.templates import DEFAULT_REFUND_TEMPLATE, REFUND_TASK_TEMPLATES

    replay.add_argument("--template", choices=tuple(REFUND_TASK_TEMPLATES),
                        default=DEFAULT_REFUND_TEMPLATE.template_id)
    replay.add_argument("--output", default="output/model-experiment")
    replay.set_defaults(handler=_model_experiment)
    decision = commands.add_parser("decision-experiment", help="Run bounded contrastive decision continuations")
    _add_policy_arguments(decision, samples=16, max_calls=400)
    decision.set_defaults(seed=100)
    decision.add_argument("--case", choices=tuple(config.name for config in demo_scenarios()),
                          default="unsafe_retry")
    decision.add_argument("--template", choices=tuple(REFUND_TASK_TEMPLATES),
                          default=DEFAULT_REFUND_TEMPLATE.template_id)
    decision.add_argument("--targets", default="consequence",
                          help="Comma-separated action, consequence, action_linked_consequence")
    decision.add_argument("--factual-seed", type=int, default=0)
    decision.add_argument("--confidence", type=float, default=0.95)
    decision.add_argument("--bootstrap-samples", type=int, default=2000)
    decision.add_argument("--bootstrap-seed", type=int, default=0)
    decision.add_argument("--interval-method", choices=("percentile_bootstrap", "wilson", "clopper_pearson"),
                          default="clopper_pearson")
    decision.add_argument("--output", default="output/decision-experiment")
    decision.set_defaults(handler=_decision_experiment)
    shapley = commands.add_parser("decision-shapley", help="Run fresh antithetic decision coalition walks")
    _add_policy_arguments(shapley, samples=1, max_calls=2000)
    shapley.set_defaults(seed=100)
    shapley.add_argument("--case", choices=tuple(config.name for config in demo_scenarios()),
                         default="clean")
    shapley.add_argument("--template", choices=tuple(REFUND_TASK_TEMPLATES),
                         default=DEFAULT_REFUND_TEMPLATE.template_id)
    shapley.add_argument("--targets", default="consequence",
                         help="Comma-separated action, consequence, action_linked_consequence")
    shapley.add_argument("--factual-seed", type=int, default=0)
    shapley.add_argument("--pairs", type=int, default=16)
    shapley.add_argument("--endpoint-samples", type=int, default=16)
    shapley.add_argument("--permutation-seed", type=int, default=0)
    shapley.add_argument("--confidence", type=float, default=0.95)
    shapley.add_argument("--interval-method", choices=("normal", "hoeffding"), default="hoeffding")
    shapley.add_argument("--endpoint-interval-method", choices=("normal", "clopper_pearson_difference"),
                         default="clopper_pearson_difference")
    shapley.add_argument("--coalition-game", choices=("strict", "on_reach"), default="strict",
                         help="strict refuses unreached held positions; on_reach records them as inactive")
    shapley.add_argument("--output", default="output/decision-shapley")
    shapley.set_defaults(handler=_decision_shapley)
    calibration = commands.add_parser("calibrate-attribution",
                                      help="Probe attribution error and coverage offline")
    calibration.add_argument("--replicates", type=int, default=32)
    calibration.add_argument("--mechanisms", help="Comma-separated registered synthetic mechanisms")
    calibration.add_argument("--samples", type=int, default=16)
    calibration.add_argument("--pairs", type=int, default=16)
    calibration.add_argument("--samples-per-eval", type=int, default=1)
    calibration.add_argument("--endpoint-samples", type=int, default=16)
    calibration.add_argument("--bootstrap-samples", type=int, default=2000)
    calibration.add_argument("--confidence", type=float, default=0.95)
    calibration.add_argument("--seed", type=int, default=100)
    calibration.add_argument("--max-calls", type=int, default=400)
    calibration.add_argument("--source-revision", help="Caller-supplied source identifier for the protocol")
    calibration.add_argument("--output", default="output/attribution-calibration")
    calibration.set_defaults(handler=_calibrate_attribution)
    comparison = commands.add_parser("compare-intervals", help="Compare intervals on shared fresh offline replays")
    comparison.add_argument("--replicates", type=int, default=32)
    comparison.add_argument("--samples", type=int, default=16)
    comparison.add_argument("--pairs", type=int, default=16)
    comparison.add_argument("--samples-per-eval", type=int, default=1)
    comparison.add_argument("--endpoint-samples", type=int, default=16)
    comparison.add_argument("--bootstrap-samples", type=int, default=2000)
    comparison.add_argument("--confidence", type=float, default=.95)
    comparison.add_argument("--seed", type=int, default=2_000_000)
    comparison.add_argument("--max-calls", type=int, default=400)
    comparison.add_argument("--source-revision")
    comparison.add_argument("--theory-only", action="store_true")
    comparison.add_argument("--output", default="output/interval-comparison")
    comparison.set_defaults(handler=_compare_intervals)
    from .benchmark.interaction_mechanisms import INTERACTION_MECHANISMS
    interactions = commands.add_parser("refund-interactions", help="Enumerate physical refund decision games")
    interactions.add_argument("--source-revision", required=True)
    interactions.add_argument("--seed", type=int, default=4_000_000)
    interactions.add_argument("--mechanism", action="append", choices=tuple(INTERACTION_MECHANISMS))
    interactions.add_argument("--output", default="output/refund-interactions")
    interactions.set_defaults(handler=_refund_interactions)
    sampling = commands.add_parser("calibrate-interactions",
                                   help="Repeat physical interaction sampling without a model")
    sampling.add_argument("--repeats", type=int, default=128)
    sampling.add_argument("--pairs", type=int, default=32)
    sampling.add_argument("--samples", type=int, default=1)
    sampling.add_argument("--endpoint-samples", type=int, default=32)
    sampling.add_argument("--confidence", type=float, default=0.95)
    sampling.add_argument("--seed", type=int, default=20_000_000)
    sampling.add_argument("--max-calls", type=int, default=1000)
    sampling.add_argument("--workers", type=int, default=1)
    sampling.add_argument("--source-revision", required=True)
    sampling.add_argument("--output", default="output/interaction-sampling")
    sampling.set_defaults(handler=_interaction_sampling)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, TypeError, OSError, InsufficientEvidenceError) as error:
        print(f"consequa-x: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
