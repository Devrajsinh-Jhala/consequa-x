"""Frozen finite-mixture refund interaction evidence; no live model calls.

Run with ``python -m consequa_x.benchmark.interaction_export --output DIR
--source-revision COMMIT`` after freezing and checking the source revision.
"""

from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from math import factorial, fsum
from pathlib import Path

from .. import __version__
from ..models import to_dict
from ..schema import get_trace_schema
from .decision_coalition import replay_decision_coalition
from .evaluation import BudgetedPolicy
from .interaction_mechanisms import COMPONENTS, INTERACTION_MECHANISMS, TARGETS
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .targets import episode_outcome


def _write(path, value):
    path.write_text(json.dumps(to_dict(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def _line(stream, value):
    stream.write((json.dumps(to_dict(value), sort_keys=True, allow_nan=False,
                            separators=(",", ":")) + "\n").encode("utf-8"))


def _shares(values):
    if any(value is None for value in values):
        return None
    return [fsum(factorial(mask.bit_count()) * factorial(2 - mask.bit_count()) / factorial(3)
                 * (values[mask | (1 << player)] - values[mask])
                 for mask in range(8) if not mask & (1 << player)) for player in range(3)]


def _summarize_case(mechanism, records):
    result = {"actual_policy_calls": sum(record["policy_calls"] for record in records), "games": {}}
    for game in ("strict", "on_reach"):
        branches = [record for record in records if record["coalition_game"] == game
                    and record["record_type"] == "branch"]
        target_summary = {}
        for target in TARGETS:
            values, statuses = [], []
            for mask in range(8):
                selected = [record for record in branches if record["mask"] == mask]
                positive = [record for record in selected if record["component_weight"] > 0]
                invalid = fsum(record["component_weight"] for record in positive
                               if record["status"] == "invalid")
                failed = fsum(record["component_weight"] for record in positive
                              if record["status"] == "failed")
                unstarted = fsum(record["component_weight"] for record in positive
                                 if record["status"] == "unstarted")
                unknown = fsum(record["component_weight"] for record in positive
                               if record["status"] == "completed"
                               and record["bad_targets"][target] is None)
                known = fsum(record["component_weight"] for record in positive
                             if record["status"] == "completed"
                             and record["bad_targets"][target] is not None)
                values.append(None if invalid or failed or unstarted or unknown else
                    fsum(record["component_weight"] * record["bad_targets"][target]
                         for record in positive))
                statuses.append({"known_mass": known, "unknown_mass": unknown,
                    "invalid_mass": invalid, "failed_mass": failed, "unstarted_mass": unstarted})
            shares = _shares(values)
            endpoint = values[7] - values[0] if values[7] is not None and values[0] is not None else None
            target_summary[target] = {"coalition_bad_rates": values, "mass_by_mask": statuses,
                "shapley_values": shares, "endpoint_difference": endpoint,
                "selection_retry_interaction": (values[3] - values[1] - values[2] + values[0]
                    if all(values[mask] is not None for mask in (0, 1, 2, 3)) else None),
                "numeric_available": shares is not None}
        result["games"][game] = {"targets": target_summary,
            "branch_status_counts": {status: sum(record["status"] == status for record in branches)
                for status in ("completed", "invalid", "failed", "unstarted")},
            "inactive_held_branch_count": sum(bool(record["inactive_held_indices"]) for record in branches),
            "reference": mechanism.analytic_reference(coalition_game=game)}
    return result


def export_refund_interactions(output, *, source_revision, seed=4_000_000, mechanisms=None):
    """Enumerate actual worlds for every component/game/mask, retaining refusals.

    Each component/game receives a separate budget, including three planted
    factual calls. Every requested mask is retained. Budgets are never redrawn
    or enlarged, and zero-mass mixture components remain in the evidence.
    ``source_revision`` is caller-supplied provenance, not inspected Git state.
    """
    if type(source_revision) is not str or not source_revision.strip():
        raise ValueError("source_revision must be a nonempty frozen source identifier")
    names = tuple(INTERACTION_MECHANISMS if mechanisms is None else mechanisms)
    if (not names or any(type(name) is not str or name not in INTERACTION_MECHANISMS for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("mechanisms must be unique known names")
    if type(seed) is not int or not 4_000_000 <= seed <= MAX_TRIAL_SEED - len(names) * 1000:
        raise ValueError("seed must reserve a disjoint valid phase window starting at 4000000 or later")
    root = Path(output)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("refund interactions require a new or empty output directory")
    root.mkdir(parents=True, exist_ok=True)
    schedule = []
    for case_index, name in enumerate(names):
        for game_index, game in enumerate(("strict", "on_reach")):
            for component_index, component in enumerate(COMPONENTS):
                first = seed + case_index * 1000 + game_index * 400 + component_index * 100
                schedule.append({"case": name, "coalition_game": game, "component_index": component_index,
                    "fresh_selection": component[0], "fresh_retry": component[1],
                    "component_weight": INTERACTION_MECHANISMS[name].component_weights()[component_index],
                    "factual_world_seed": first, "factual_policy_seed": first,
                    "branch_continuation_seeds_by_mask": [first + 1 + mask for mask in range(8)],
                    "max_calls": INTERACTION_MECHANISMS[name].max_calls})
    _write(root / "protocol.json", {"package_version": __version__, "source_revision": source_revision,
        "source_revision_trust": "caller supplied; exporter does not inspect Git",
        "design": "full four-component deterministic mixture, each of eight held masks, both games",
        "sampling_claim": "finite enumeration of a declared Bernoulli population law; not stochastic observations",
        "seed": seed, "model_phase_rule": "world/model schedule seed * 6 + reached position",
        "mask_order": list(range(8)), "targets": TARGETS, "schedule": schedule,
        "cases": {name: to_dict(INTERACTION_MECHANISMS[name]) for name in names},
        "retention": "every planned branch including failed, invalid, unstarted and zero-weight components",
        "budget_rule": "per component/game budget includes three factual calls; stop starting slots at exhaustion",
        "references": {name: {game: INTERACTION_MECHANISMS[name].analytic_reference(coalition_game=game)
                              for game in ("strict", "on_reach")} for name in names},
        "limitations": ["synthetic public-only policy, no live model or independence claim",
            "exact mixture law does not validate finite permutation sampling",
            "held decision effects are positional policy interventions, not context/fault attribution",
            "zero-weight components are evidence only and do not change the population expectation"]})
    _write(root / "trace-schema.json", get_trace_schema())
    retained = {name: [] for name in names}
    with ExitStack() as stack:
        raw = stack.enter_context((root / "evidence.jsonl.gz").open("wb"))
        evidence = stack.enter_context(gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0))
        raw_gold = stack.enter_context((root / "evaluator-truth.jsonl.gz").open("wb"))
        gold = stack.enter_context(gzip.GzipFile(filename="", fileobj=raw_gold, mode="wb", mtime=0))
        for entry in schedule:
            name, game = entry["case"], entry["coalition_game"]
            mechanism = INTERACTION_MECHANISMS[name]
            component = (entry["fresh_selection"], entry["fresh_retry"])
            policy = mechanism.make_policy(factual_policy_seed=entry["factual_policy_seed"], component=component)
            budget = BudgetedPolicy(policy, entry["max_calls"])
            factual = run_policy_scenario(mechanism.scenario_config(), budget,
                seed=entry["factual_world_seed"], policy_seed=entry["factual_policy_seed"], max_attempts=2)
            base = {"case": name, "coalition_game": game, "component_index": entry["component_index"],
                    "component_weight": entry["component_weight"], "policy_metadata": policy.metadata}
            factual_record = {**base, "record_type": "factual", "policy_calls": budget.calls,
                "trace": factual.trace.to_dict(), "explanation": factual.explanation.to_dict()}
            _line(evidence, factual_record)
            retained[name].append(factual_record)
            _line(gold, {**base, "record_type": "factual", "seed": factual.seed,
                        "config": to_dict(factual.config), "records": to_dict(factual.ground_truth)})
            for mask, continuation_seed in enumerate(entry["branch_continuation_seeds_by_mask"]):
                held = tuple(index for index in range(3) if mask & (1 << index))
                record = {**base, "record_type": "branch", "mask": mask,
                    "held_indices": list(held), "continuation_seed": continuation_seed,
                    "policy_calls": 0, "inactive_held_indices": [], "decisions": [],
                    "status": "unstarted", "bad_targets": {target: None for target in TARGETS},
                    "trace": None, "explanation": None}
                if budget.calls < budget.max_calls:
                    replay = replay_decision_coalition(factual, budget, held_indices=held,
                        continuation_seed=continuation_seed, coalition_game=game)
                    record.update(status=replay.status, summary=replay.summary(),
                        decisions=to_dict(replay.decisions), policy_calls=replay.policy_calls,
                        inactive_held_indices=list(replay.inactive_held_indices))
                    if replay.episode is not None:
                        outcome = episode_outcome(replay.episode)
                        record.update(trace=replay.episode.trace.to_dict(),
                            explanation=replay.episode.explanation.to_dict(),
                            bad_targets={target: (None if outcome.target_value(target) is None else
                                                 int(not outcome.target_value(target))) for target in TARGETS})
                        _line(gold, {**base, "record_type": "branch", "mask": mask,
                            "seed": replay.episode.seed, "config": to_dict(replay.episode.config),
                            "records": to_dict(replay.episode.ground_truth)})
                record.update(budget_calls_after=budget.calls, budget_max_calls=budget.max_calls)
                _line(evidence, record)
                retained[name].append(record)
    summary = {"design": "exact deterministic-mixture world enumeration",
        "cases": {name: _summarize_case(INTERACTION_MECHANISMS[name], retained[name]) for name in names},
        "actual_policy_calls": sum(record["policy_calls"] for rows in retained.values() for record in rows),
        "additional_reference_policy_calls": 0,
        "completed": True}
    _write(root / "summary.json", summary)
    text = ["# Refund interaction enumeration", "", "This artifact enumerates four deterministic fresh-choice components, all eight held masks, and both explicitly named games. It is not a set of live stochastic samples.", "",
        "The factual refund, retry and final stop are planted. All targets come from actual payment readback; evaluator records are stored separately.", "",
        "| Case | Game | Consequence shares | Interaction |", "| --- | --- | --- | --- |"]
    for name, item in summary["cases"].items():
        for game, result in item["games"].items():
            target = result["targets"]["consequence"]
            text.append(f"| {name} | {game} | {target['shapley_values']} | {target['selection_retry_interaction']} |")
    text += ["", f"Actual synthetic policy calls: {summary['actual_policy_calls']}.", "",
        "A positive invalid, unknown, failed or unstarted mixture weight refuses the numerical vector. Budget controls retain the reference law while refusing incomplete enumerations. Zero-weight components remain in the evidence but do not affect that law.", "",
        "Run the independent auditor in `scripts/audit_refund_interactions.py` against this directory. Permutation-sampler accuracy, live-model studies, context/fault attribution and cross-domain recovery require separate experiments."]
    (root / "README.md").write_text("\n".join(text) + "\n", encoding="utf-8", newline="\n")
    _write(root / "manifest.json", {"package_version": __version__,
        "completed": True, "status": "completed", "artifacts": [
            {"path": path.relative_to(root).as_posix(),
             "sha256": sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
            for path in sorted(root.rglob("*")) if path.is_file() and path != root / "manifest.json"]})
    return summary


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--seed", type=int, default=4_000_000)
    parser.add_argument("--mechanism", action="append", choices=tuple(INTERACTION_MECHANISMS))
    args = parser.parse_args(argv)
    result = export_refund_interactions(args.output, source_revision=args.source_revision,
                                       seed=args.seed, mechanisms=args.mechanism)
    print(json.dumps({"output": str(Path(args.output).resolve()),
                      "actual_policy_calls": result["actual_policy_calls"]}, sort_keys=True))


if __name__ == "__main__":
    main()
