"""Independent saved-evidence audit; never executes a policy or a replayer."""

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import NormalDist

import jsonschema
from consequa_x.explanation import explain
from consequa_x.models import Trace
from consequa_x.verification import verify


EXPECTED_NAMES = (
    "protective-stop-q10", "protective-stop-q50", "protective-stop-q90",
    "retry-pivot-q10", "retry-pivot-q50", "retry-pivot-q90",
    "idempotent-stop-q50", "unknown-provenance-stop-q50", "lagged-readback-stop-q50",
    "budget-stop-q50",
)
TARGETS = ("action", "consequence", "action_linked_consequence")
counts = Counter()
totals = Counter()
branch_totals = defaultdict(Counter)
branch_target_totals = defaultdict(Counter)
row_values = defaultdict(list)
row_statuses = defaultdict(Counter)
endpoint_values = defaultdict(list)
endpoint_statuses = defaultdict(Counter)
locus_counts = defaultdict(Counter)
replicate_zero = {}


def close(actual, expected, label):
    if expected is None:
        assert actual is None, (label, actual, expected)
    elif isinstance(expected, (list, tuple)):
        assert isinstance(actual, (list, tuple)) and len(actual) == len(expected), label
        for i, (left, right) in enumerate(zip(actual, expected)):
            close(left, right, (label, i))
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert actual is not None and math.isclose(actual, expected, abs_tol=1e-12, rel_tol=1e-12), (
            label, actual, expected,
        )
    else:
        assert actual == expected, (label, actual, expected)


def load(path):
    if path.suffix == ".gz":
        assert path.read_bytes()[4:8] == b"\0\0\0\0", path.name
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def settings(name):
    return {
        "q": int(name.split("q")[-1]) / 100,
        "retry_factual": name.startswith("retry-pivot"),
        "idempotent": name.startswith("idempotent"),
        "no_provenance": name.startswith("unknown-provenance"),
        "lagged": name.startswith("lagged"),
    }


def outcomes(name, retry):
    s = settings(name)
    duplicate = retry and not s["idempotent"]
    return {
        "action": True,
        "consequence": None if s["lagged"] else not duplicate,
        "action_linked_consequence": (
            None if s["lagged"] or (s["no_provenance"] and not duplicate) else not duplicate
        ),
    }


def reference(name, method, target, position=None):
    s = settings(name)
    n = 3 if s["retry_factual"] else 2
    unknown = target != "action" and (
        s["lagged"] or target == "action_linked_consequence" and s["no_provenance"]
    )
    if unknown:
        return None
    if method == "endpoint":
        return 0. if target == "action" or s["idempotent"] else (
            1 - s["q"] if s["retry_factual"] else -s["q"]
        )
    if method == "shapley":
        if n == 3:
            return None
        return 0. if target == "action" or s["idempotent"] or position == 0 else -s["q"]
    if target == "action" or s["idempotent"]:
        return 0.
    return (0. if position == 2 else s["q"] - 1) if s["retry_factual"] else s["q"]


def variance(values):
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def normal_interval(values, confidence):
    mean = sum(values) / len(values)
    margin = NormalDist().inv_cdf((1 + confidence) / 2) * math.sqrt(variance(values) / len(values))
    return mean - margin, mean + margin


def percentile(values, probability):
    index = (len(values) - 1) * probability
    lo = int(index)
    if lo == len(values) - 1:
        return values[lo]
    return values[lo] + (values[lo + 1] - values[lo]) * (index - lo)


def bootstrap_interval(values, factual_bad, seed, confidence, replicates):
    rng = random.Random(seed)
    draws = []
    for _ in range(replicates):
        sampled = [values[rng.randrange(len(values))] for _ in values]
        draws.append(sum(sampled) / len(sampled) - int(factual_bad))
    draws.sort()
    tail = (1 - confidence) / 2
    return percentile(draws, tail), percentile(draws, 1 - tail)


def branch_label(branch, target):
    if branch["status"] != "completed":
        return branch["status"]
    return "unknown" if branch["target_values"][target] is None else "known"


def bad(branch, target):
    value = branch["target_values"][target]
    return float(not value) if value is not None else None


def slots_for(trial, plan):
    seed_plan = trial["seed_plan"]
    n = seed_plan["decision_count"]
    slots = []
    for role, held in (("endpoint_empty", []), ("endpoint_full", list(range(n)))):
        for sample in range(plan["endpoint_samples"]):
            slots.append({"index": len(slots), "role": role, "pair_index": None,
                          "walk": None, "step": None, "held_indices": held,
                          "sample_index": sample,
                          "continuation_seed": seed_plan["shapley_seed"] + len(slots)})
    rng = random.Random(seed_plan["permutation_seed"])
    permutations = []
    for pair in range(plan["pairs"]):
        order = list(range(n))
        rng.shuffle(order)
        permutations.append(order)
        for walk, permutation in (("forward", order), ("reverse", order[::-1])):
            for step in range(n + 1):
                held = sorted(permutation[:step])
                for sample in range(plan["samples_per_eval"]):
                    slots.append({"index": len(slots), "role": "walk", "pair_index": pair,
                                  "walk": walk, "step": step, "held_indices": held,
                                  "sample_index": sample,
                                  "continuation_seed": seed_plan["shapley_seed"] + len(slots)})
    assert trial["shapley"]["permutations"] == permutations
    assert trial["shapley"]["slots"] == slots
    return slots, permutations


def check_branches(trial, method, plan):
    name, seed_plan = trial["seed_plan"]["mechanism"], trial["seed_plan"]
    s = settings(name)
    n = seed_plan["decision_count"]
    result = trial[method]
    assert result is not None, (name, method)
    if method == "shapley":
        slots, permutations = slots_for(trial, plan)
    else:
        slots, permutations = None, None
    expected_count = seed_plan[f"{method}_branches"]
    assert len(result["branches"]) == expected_count
    actual_calls = 0
    for index, branch in enumerate(result["branches"]):
        if method == "contrastive":
            assert branch["index"] == index
            assert branch["decision_index"] == index // plan["samples"]
            held = set(range(branch["decision_index"]))
            seed = seed_plan["contrastive_seed"] + index
            assert branch["continuation_seed"] == seed
        else:
            assert branch["slot_index"] == index
            held, seed = set(slots[index]["held_indices"]), slots[index]["continuation_seed"]
        receipts = branch["reached_decisions"]
        assert branch["policy_calls"] == sum(receipt["policy_calls"] for receipt in receipts)
        actual_calls += branch["policy_calls"]
        for number, receipt in enumerate(receipts):
            assert receipt["index"] == number
            assert receipt["stage"] == ("select" if number == 0 else "after_response")
            assert receipt["continuation_model_seed"] == seed * 6 + number
            assert receipt["source"] == ("held_factual" if number in held else "resampled")
            if receipt["source"] == "held_factual":
                assert receipt["policy_calls"] == 0
            if number < n:
                assert receipt["factual_model_seed"] == seed_plan["factual_seed"] * 6 + number
                assert receipt["factual_event_id"] == ("refund_decision" if number == 0 else f"response_decision_{number}")
            else:
                assert receipt["factual_model_seed"] is receipt["factual_event_id"] is None
        if name == "budget-stop-q50":
            if index == 0:
                assert branch["status"] == "failed" and branch["budget_exhausted"]
                assert branch["error_type"] == "CallBudgetExceeded"
                assert len(receipts) == 2 and receipts[0]["policy_calls"] == 1 and receipts[1]["policy_calls"] == 0
                assert branch["target_values"] is None
            else:
                assert branch["status"] == "unstarted" and not receipts
                assert branch["policy_calls"] == 0 and branch["target_values"] is None
        else:
            retry = s["retry_factual"] if 1 in held else random.Random(seed * 6 + 1).random() < s["q"]
            length = 3 if retry else 2
            assert len(receipts) == length
            assert branch["policy_calls"] == length - len(held.intersection(range(length)))
            if 2 in held and not retry:
                assert branch["status"] == "invalid" and branch["error_type"] == "DecisionCoalitionUnreachable"
                assert branch["unreached_held_indices"] == [2]
                assert branch["target_values"] is None
            else:
                assert branch["status"] == "completed"
                assert branch["target_values"] == outcomes(name, retry)
                counts["independent_target_labels"] += len(TARGETS)
        label = (name, method)
        branch_totals[label][branch["status"]] += 1
        if branch["status"] == "completed":
            for target in TARGETS:
                branch_target_totals[(name, method, target)][branch_label(branch, target)] += 1
        counts["planned_branches"] += 1
    assert actual_calls == trial["calls"][method]
    assert actual_calls + trial["calls"][f"{method}_factual"] <= seed_plan["max_calls"]
    return slots, permutations


def check_contrastive(trial, plan):
    name, n = trial["seed_plan"]["mechanism"], trial["seed_plan"]["decision_count"]
    result = trial["contrastive"]
    expected_factual = outcomes(name, settings(name)["retry_factual"])
    for estimate in result["results"]:
        position, target = estimate["decision_index"], estimate["target"]
        branches = result["branches"][position * plan["samples"]:(position + 1) * plan["samples"]]
        labels = Counter(branch_label(branch, target) for branch in branches)
        factual_bad = None if expected_factual[target] is None else not expected_factual[target]
        assert estimate["factual_bad"] == factual_bad
        for label in ("known", "unknown", "failed", "unstarted"):
            assert estimate[f"{label}_samples"] == labels[label]
        estimable = factual_bad is not None and labels["known"] == plan["samples"]
        assert estimate["status"] == ("estimated" if estimable else "refused")
        if estimable:
            values = [bad(branch, target) for branch in branches]
            point = sum(values) / len(values) - int(factual_bad)
            close(estimate["effect"], point, (name, position, target, "effect"))
            close(estimate["changed_bad_rate"], sum(values) / len(values), "changed rate")
            if len(set(values)) == 1:
                expected_interval = (point, point)
            elif trial["seed_plan"]["replicate"] == 0:
                expected_interval = bootstrap_interval(values, factual_bad, trial["seed_plan"]["bootstrap_seed"],
                                                       plan["confidence"], plan["bootstrap_samples"])
                counts["independent_bootstrap_intervals"] += 1
            else:
                expected_interval = estimate["confidence_interval"]
            close(estimate["confidence_interval"], expected_interval, "contrastive interval")
            assert estimate["significant_rescue"] == (point < 0 and estimate["confidence_interval"][1] < 0)
        else:
            assert estimate["effect"] is estimate["confidence_interval"] is estimate["changed_bad_rate"] is None
        key = (name, "contrastive", target, position)
        row_statuses[key][estimate["status"]] += 1
        if estimable:
            row_values[key].append((estimate["effect"], estimate["confidence_interval"]))
        counts["contrastive_estimates"] += 1
    assert len(result["results"]) == n * len(TARGETS)
    for locus in result["loci"]:
        estimates = [estimate for estimate in result["results"] if estimate["target"] == locus["target"]]
        if any(estimate["status"] == "refused" for estimate in estimates):
            expected = "refused"
        else:
            rescued = [estimate["decision_index"] for estimate in estimates if estimate["significant_rescue"]]
            expected = str(max(rescued)) if rescued else "no_rescue"
        actual = str(locus["decision_index"]) if locus["status"] == "identified" else locus["status"]
        assert actual == expected
        locus_counts[(name, locus["target"])][actual] += 1


def check_shapley(trial, plan, slots, permutations):
    name, n = trial["seed_plan"]["mechanism"], trial["seed_plan"]["decision_count"]
    result = trial["shapley"]
    branches = result["branches"]
    for target in TARGETS:
        pair_vectors = []
        for pair, order in enumerate(permutations):
            chosen = [slot for slot in slots if slot["role"] == "walk" and slot["pair_index"] == pair]
            labels = [branch_label(branches[slot["index"]], target) for slot in chosen]
            if any(label != "known" for label in labels):
                pair_vectors.append(None)
                continue
            vector = [0.] * n
            for walk, permutation in (("forward", order), ("reverse", order[::-1])):
                means = [sum(bad(branches[slot["index"]], target) for slot in chosen
                             if slot["walk"] == walk and slot["step"] == step) / plan["samples_per_eval"]
                         for step in range(n + 1)]
                for step, index in enumerate(permutation):
                    vector[index] += (means[step + 1] - means[step]) * .5
            pair_vectors.append(vector)
        estimable = all(vector is not None for vector in pair_vectors)
        estimates = [estimate for estimate in result["results"] if estimate["target"] == target]
        for position, estimate in enumerate(estimates):
            assert estimate["decision_index"] == position
            expected_pairs = [vector[position] if vector is not None else None for vector in pair_vectors]
            close(estimate["pair_values"], expected_pairs, "pair values")
            assert estimate["status"] == ("estimated" if estimable else "refused")
            if estimable:
                close(estimate["shapley_value"], sum(expected_pairs) / len(expected_pairs), "Shapley point")
                close(estimate["confidence_interval"], normal_interval(expected_pairs, plan["confidence"]), "Shapley interval")
            else:
                assert estimate["shapley_value"] is estimate["confidence_interval"] is None
            key = (name, "shapley", target, position)
            row_statuses[key][estimate["status"]] += 1
            if estimable:
                row_values[key].append((estimate["shapley_value"], estimate["confidence_interval"]))
            counts["shapley_estimates"] += 1
        endpoint = next(item for item in result["endpoint_checks"] if item["target"] == target)
        endpoints = [[branches[slot["index"]] for slot in slots if slot["role"] == role]
                     for role in ("endpoint_empty", "endpoint_full")]
        endpoint_ok = all(branch_label(branch, target) == "known" for group in endpoints for branch in group)
        assert endpoint["status"] == ("estimated" if endpoint_ok else "refused")
        if endpoint_ok:
            empty, full = [[bad(branch, target) for branch in group] for group in endpoints]
            effect = sum(full) / len(full) - sum(empty) / len(empty)
            margin = NormalDist().inv_cdf((1 + plan["confidence"]) / 2) * math.sqrt(
                variance(empty) / len(empty) + variance(full) / len(full))
            close(endpoint["endpoint_difference"], effect, "endpoint point")
            close(endpoint["confidence_interval"], (effect - margin, effect + margin), "endpoint interval")
            endpoint_values[(name, target)].append((effect, endpoint["confidence_interval"]))
        else:
            assert endpoint["endpoint_difference"] is endpoint["confidence_interval"] is None
        expected_sum = sum(item["shapley_value"] for item in estimates) if estimable else None
        close(endpoint["coefficient_sum"], expected_sum, "coefficient sum")
        close(endpoint["discrepancy"], expected_sum - endpoint["endpoint_difference"] if estimable and endpoint_ok else None,
              "endpoint discrepancy")
        endpoint_statuses[(name, target)][endpoint["status"]] += 1
        counts["endpoint_checks"] += 1


def metric_check(row, observations, truth, planned, confidence):
    estimated = len(observations)
    assert row["estimated_trials"] == estimated and row["refused_trials"] == planned - estimated
    assert row["reference_eligible_trials"] == (planned if truth is not None else 0)
    assert row["reference_ineligible_trials"] == (0 if truth is not None else planned)
    close(row["reference"], truth, "population reference")
    errors = [point - truth for point, _ in observations] if truth is not None else []
    assert row["scored_estimates"] == len(errors)
    assert row["eligible_unscored_trials"] == (planned - len(errors) if truth is not None else 0)
    bias = sum(errors) / len(errors) if errors else None
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors)) if errors else None
    close(row["bias"], bias, "bias")
    close(row["rmse"], rmse, "RMSE")
    bias_se = math.sqrt(variance(errors) / len(errors)) if len(errors) >= 2 else None
    squared = [error * error for error in errors]
    rmse_se = math.sqrt(variance(squared) / len(squared)) / (2 * rmse) if len(errors) >= 2 and rmse else None
    close(row["bias_mcse"], bias_se, "bias MCSE")
    close(row["rmse_mcse"], rmse_se, "RMSE MCSE")
    intervals = [interval for _, interval in observations] if truth is not None else []
    covered = sum(low <= truth <= high for low, high in intervals)
    assert row["interval_coverage"]["numerator"] == covered
    assert row["interval_coverage"]["denominator"] == len(intervals)
    assert row["interval_coverage_including_refusals"]["numerator"] == covered
    assert row["interval_coverage_including_refusals"]["denominator"] == (planned if truth is not None else 0)
    assert row["degenerate_intervals"] == sum(low == high for _, (low, high) in observations)
    for field, numerator, denominator in (
        ("availability_rate", estimated, planned), ("refusal_rate", planned - estimated, planned),
        ("interval_coverage", covered, len(intervals)),
        ("interval_coverage_including_refusals", covered, planned if truth is not None else 0),
    ):
        metric = row[field]
        assert metric["numerator"] == numerator and metric["denominator"] == denominator
        if denominator:
            p = numerator / denominator
            z2 = NormalDist().inv_cdf((1 + confidence) / 2) ** 2
            center = (p + z2 / (2 * denominator)) / (1 + z2 / denominator)
            margin = math.sqrt(z2 * (p * (1 - p) / denominator + z2 / (4 * denominator ** 2))) / (1 + z2 / denominator)
            close(metric["rate"], p, "metric rate")
            close(metric["confidence_interval"], (0. if numerator == 0 else center - margin,
                                                 1. if numerator == denominator else center + margin), "Wilson interval")
        else:
            assert metric["rate"] is metric["confidence_interval"] is None


def public_is_separate(value):
    if isinstance(value, dict):
        assert not {"ground_truth", "fault", "fault_applied", "cache_hit"}.intersection(value)
        for child in value.values():
            public_is_separate(child)
    elif isinstance(value, list):
        for child in value:
            public_is_separate(child)


def check_full_evidence(root, name, validator):
    public = load(root / "evidence" / f"{name}.json.gz")
    gold = load(root / "evaluator_truth" / f"{name}.json.gz")
    compact = replicate_zero[name]
    assert public["seed_plan"] == gold["seed_plan"] == compact["seed_plan"]
    public_is_separate(public)
    for method in ("contrastive", "shapley"):
        reached = {f"branch_{index}": branch for index, branch in enumerate(compact[method]["branches"])
                   if branch["status"] != "unstarted"}
        expected = {"factual"} | reached.keys()
        assert set(public["methods"][method]) == expected
        completed_keys = set()
        for key, record in public["methods"][method].items():
            if key != "factual":
                branch = reached[key]
                assert len(record["decisions"]) == len(branch["reached_decisions"])
                for full, receipt in zip(record["decisions"], branch["reached_decisions"]):
                    for field, value in receipt.items():
                        assert full[field] == value
                assert ("trace" in record) == (branch["status"] == "completed")
            if "trace" not in record:
                assert key not in gold["methods"][method]
                assert "explanation" not in record
                counts["full_partial_receipts"] += 1
                continue
            trace_data = record["trace"]
            validator.validate(trace_data)
            trace = Trace.from_dict(trace_data)
            assert trace.to_dict() == trace_data
            assert verify(trace.action, trace.observations[-1]).to_dict() == trace.verifications[-1].to_dict()
            assert explain(trace).to_dict() == record["explanation"]
            completed_keys.add(key)
            if key == "factual":
                expected_hash = compact["factual"][method]["trace_sha256"]
                canonical = json.dumps(trace_data, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True, allow_nan=False).encode("utf-8")
                assert hashlib.sha256(canonical).hexdigest() == expected_hash
            selected = [event for event in trace_data["events"] if event["type"] == "agent_decision"]
            assert selected[0]["data"]["policy_reply"]["decision"]["operation"] == "refund"
            actual_retry = selected[1]["data"]["policy_reply"]["decision"]["operation"] == "retry"
            expected_values = outcomes(name, actual_retry)
            if key != "factual":
                assert reached[key]["target_values"] == expected_values
            gold_record = gold["methods"][method][key]
            assert gold_record["seed"] == compact["seed_plan"]["factual_seed"]
            refunds = [item for item in gold_record["records"] if item["kind"] == "refund"]
            attempts = [item for item in gold_record["records"] if item["kind"] == "execution_attempt"]
            expected_refunds = 1 + int(actual_retry and not settings(name)["idempotent"])
            assert len(refunds) == expected_refunds
            assert len(attempts) == len(trace_data["responses"]) == 1 + int(actual_retry)
            assert [item["fault"] for item in attempts] == ["timeout_after_commit"] + (["clean"] if actual_retry else [])
            if actual_retry and settings(name)["idempotent"]:
                assert attempts[1]["cache_hit"] is True and not attempts[1]["committed_effect_ids"]
            for event in selected:
                metadata = event["data"]["policy"]
                assert metadata["conditioning"]["naturally_sampled_factual"] is False
                assert metadata["conditioning"]["reserved_timeout_model_seed"] == compact["seed_plan"]["factual_seed"] * 6 + 1
                assert metadata["hidden_evidence_inputs"] is False
            counts["schema_strict_roundtrip_traces"] += 1
            counts["recomputed_explanations"] += 1
            counts["recomputed_verifications"] += 1
            counts["separate_gold_records"] += 1
        assert set(gold["methods"][method]) == completed_keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root
    protocol = load(root / "protocol.json")
    manifest = load(root / "manifest.json")
    assert manifest["status"] == "completed", "Do not audit incomplete exports"
    assert protocol["source_revision"] == args.source
    plan = protocol["plan"]
    assert tuple(plan["mechanisms"]) == EXPECTED_NAMES and tuple(plan["targets"]) == TARGETS
    repeats = plan["repeats"]
    for artifact in manifest["artifacts"]:
        path = root / artifact["path"]
        assert path.is_file() and path.stat().st_size == artifact["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        counts["manifest_artifacts"] += 1
    expected_total_seeds = sum(
        1 + (3 if settings(name)["retry_factual"] else 2) * plan["samples"] +
        2 * plan["endpoint_samples"] + 2 * plan["pairs"] *
        ((3 if settings(name)["retry_factual"] else 2) + 1) * plan["samples_per_eval"]
        for name in EXPECTED_NAMES
    ) * repeats
    inference_start = 6 * (plan["seed"] + expected_total_seeds)
    cursor = plan["seed"]
    schedule = protocol["trial_schedule"]
    assert len(schedule) == len(EXPECTED_NAMES) * repeats == protocol["planned_trials"]
    for name in EXPECTED_NAMES:
        path = root / "trials" / f"{name}.jsonl.gz"
        assert path.read_bytes()[4:8] == b"\0\0\0\0"
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            trials_seen = 0
            for replicate, line in enumerate(stream):
                trial = json.loads(line)
                n = 3 if settings(name)["retry_factual"] else 2
                contrastive_count = n * plan["samples"]
                shapley_count = 2 * plan["endpoint_samples"] + 2 * plan["pairs"] * (n + 1) * plan["samples_per_eval"]
                index = counts["trials"]
                expected_seed_plan = {"index": index, "mechanism": name, "replicate": replicate,
                    "decision_count": n, "factual_seed": cursor, "contrastive_seed": cursor + 1,
                    "contrastive_branches": contrastive_count,
                    "shapley_seed": cursor + 1 + contrastive_count, "shapley_branches": shapley_count,
                    "permutation_seed": inference_start + 2 * index,
                    "bootstrap_seed": inference_start + 2 * index + 1,
                    "max_calls": 3 if name == "budget-stop-q50" else plan["max_calls"]}
                assert trial["seed_plan"] == schedule[index] == expected_seed_plan
                cursor += 1 + contrastive_count + shapley_count
                assert trial["errors"] == []
                assert trial["factual"]["contrastive"] == trial["factual"]["shapley"]
                expected_factual = outcomes(name, settings(name)["retry_factual"])
                factual_keys = ("action_selected", "consequence_satisfied", "action_linked_consequence_satisfied")
                for method in ("contrastive", "shapley"):
                    factual = trial["factual"][method]
                    assert factual["status"] == "completed" and factual["calls"] == n
                    assert factual["targets"] == dict(zip(factual_keys, expected_factual.values()))
                    assert len(factual["decisions"]) == n
                    for number, decision in enumerate(factual["decisions"]):
                        assert decision["seed"] == expected_seed_plan["factual_seed"] * 6 + number
                        assert decision["error_type"] is decision["error"] is None
                        assert decision["reply"]["decision"]["operation"] == (
                            "refund" if number == 0 else "retry" if number == 1 and settings(name)["retry_factual"] else "stop")
                    counts["factual_captures"] += 1
                    counts["paired_factual_matches"] += int(method == "shapley")
                for key in ("contrastive_factual", "shapley_factual"):
                    assert trial["calls"][key] == n
                assert trial["calls"]["factual"] == 2 * n
                assert trial["calls"]["total"] == sum(trial["calls"][key] for key in (
                    "contrastive_factual", "shapley_factual", "contrastive", "shapley"))
                check_branches(trial, "contrastive", plan)
                slots, permutations = check_branches(trial, "shapley", plan)
                check_contrastive(trial, plan)
                check_shapley(trial, plan, slots, permutations)
                for key in ("factual", "contrastive", "shapley", "total"):
                    totals[key] += trial["calls"][key]
                if replicate == 0:
                    replicate_zero[name] = trial
                counts["trials"] += 1
                trials_seen += 1
            assert trials_seen == repeats
        print(f"Audited all {repeats} retained trials for {name}", flush=True)
    assert cursor == plan["seed"] + expected_total_seeds
    assert inference_start > 6 * (cursor - 1) + 5
    assert sum(sum(branch_totals[(name, "contrastive")].values()) for name in EXPECTED_NAMES) == protocol["planned_contrastive_branches"]
    assert sum(sum(branch_totals[(name, "shapley")].values()) for name in EXPECTED_NAMES) == protocol["planned_shapley_branches"]
    summary = load(root / "summary.json")
    assert summary["planned_trials"] == summary["retained_trials"] == counts["trials"]
    assert summary["factual_failures"] == summary["paired_factual_disagreements"] == 0
    assert summary["actual_policy_calls"] == dict(totals)
    for row in summary["estimates"]:
        key = (row["mechanism"], row["method"], row["target"], row["decision_index"])
        assert sum(row_statuses[key].values()) == repeats
        truth = reference(*key)
        metric_check(row, row_values[key], truth, repeats, plan["confidence"])
        assert row["estimated_trials"] == row_statuses[key]["estimated"]
        if truth == 0:
            exclusions = sum(low > 0 or high < 0 for _, (low, high) in row_values[key])
            assert row["zero_reference_interval_exclusion"]["numerator"] == exclusions
            assert row["zero_reference_interval_exclusion"]["denominator"] == len(row_values[key])
        counts["summary_estimate_rows"] += 1
    for row in summary["endpoints"]:
        key = (row["mechanism"], row["target"])
        truth = reference(key[0], "endpoint", key[1])
        metric_check(row, endpoint_values[key], truth, repeats, plan["confidence"])
        assert row["estimated_trials"] == endpoint_statuses[key]["estimated"]
        counts["summary_endpoint_rows"] += 1
    for row in summary["loci"]:
        key = (row["mechanism"], row["target"])
        actual = Counter(row["selection_counts"])
        assert actual == locus_counts[key]
        eligible = reference(key[0], "contrastive", key[1], 0) is not None
        expected = 1 if settings(key[0])["retry_factual"] and key[1] != "action" else None
        assert row["latest_population_rescue"] == (expected if eligible else None)
        assert row["reference_eligible_trials"] == (repeats if eligible else 0)
        matches = locus_counts[key][str(expected) if expected is not None else "no_rescue"] if eligible else 0
        assert row["population_rule_match_including_refusals"]["numerator"] == matches
        assert row["population_rule_match_including_refusals"]["denominator"] == (repeats if eligible else 0)
        counts["summary_locus_rows"] += 1
    for row in summary["branches"]:
        key = (row["mechanism"], row["method"])
        assert Counter(row["status_counts"]) == branch_totals[key]
        for target in TARGETS:
            assert Counter(row["completed_target_outcomes"][target]) == branch_target_totals[(*key, target)]
    schema = load(root / "trace-schema.json")
    validator_class = jsonschema.validators.validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema)
    for name in EXPECTED_NAMES:
        check_full_evidence(root, name, validator)
        counts["full_evidence_strata"] += 1
    report = {"audit_passed": True, "source_revision": args.source,
              "scope": "independent saved-evidence audit; no inference or redraw",
              "counts": dict(counts), "actual_policy_calls": dict(totals),
              "independent_checks": [
                  "complete globally disjoint factual, continuation, permutation and bootstrap schedule",
                  "all compact phase-key coin outcomes, typed targets and unreachable held tails",
                  "paired factual equality, reached receipt identities, zero held calls and budget sums",
                  "all contrastive points/refusals/loci; representative bootstrap intervals plus all degenerate intervals",
                  "all pair-level Shapley values, nominal intervals and independent endpoints",
                  "population reference eligibility, bias, RMSE, MCSE, coverage and Wilson denominators",
                  "all replicate-0 schemas, strict trace roundtrips, verifier and explanation recomputation",
                  "separate evaluator truth; every attempted partial branch retained without invented trace",
                  "completed exporter byte manifest and deterministic gzip headers",
              ], "limitations": [
                  "Nondegenerate contrastive bootstrap intervals are independently recomputed for preselected replicate 0 only.",
                  "Strict and verifier checks reuse public production record/evidence validators, not analytic or scoring helpers.",
                  "Byte hashes identify retained bytes, not authenticity or population generalization.",
              ]}
    if args.output is not None:
        assert not args.output.exists(), "Audit output must not overwrite retained evidence"
        args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
