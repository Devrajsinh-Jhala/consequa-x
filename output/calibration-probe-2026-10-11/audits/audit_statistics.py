"""Independent, standard-library audit of a completed retained calibration export.

This script imports neither Consequa-X nor its analytic reference/scorer.  It
derives refund truth from the declared mechanism names and reconciles all
inference inputs with compact reached-decision receipts.  Run only after the
exporter has closed every gzip stream and written its completed manifest.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import re
from statistics import NormalDist, mean, variance
import time


CHECKS = 0
BOOTSTRAP_CACHE = {}
TARGETS = ("action", "consequence", "action_linked_consequence")
FIELDS = {"action": "action_selected", "consequence": "consequence_satisfied",
          "action_linked_consequence": "action_linked_consequence_satisfied"}


def checked(condition, label):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(label)


def compare(actual, expected, label):
    if isinstance(expected, dict):
        checked(isinstance(actual, dict), label + ": expected object")
        for key, value in expected.items():
            checked(key in actual, label + ": missing " + key)
            compare(actual[key], value, label + "/" + key)
    elif isinstance(expected, (list, tuple)):
        checked(isinstance(actual, (list, tuple)) and len(actual) == len(expected), label + ": sequence size")
        for index, value in enumerate(expected):
            compare(actual[index], value, f"{label}/{index}")
    elif type(expected) is float:
        checked(type(actual) in (int, float) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=2e-12),
                f"{label}: {actual!r} != {expected!r}")
    else:
        checked(actual == expected and (type(expected) is not bool or type(actual) is bool),
                f"{label}: {actual!r} != {expected!r}")


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def decode(text):
    return json.loads(text, object_pairs_hook=object_pairs,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def load(path):
    return decode(path.read_text(encoding="utf-8"))


def mechanism(name):
    q = int(re.search(r"q(\d+)$", name).group(1)) / 100
    return {"q": q, "retry": name.startswith("retry-pivot"),
            "idempotent": name.startswith("idempotent"),
            "provenance": not name.startswith("unknown-provenance"),
            "lagged": name.startswith("lagged-readback"),
            "budget": name.startswith("budget-stop"),
            "n": 3 if name.startswith("retry-pivot") else 2}


def truth(name, target):
    m = mechanism(name)
    n, q = m["n"], m["q"]
    valid = [q if n == 3 and mask & 4 and not mask & 2 else 1.0 for mask in range(1 << n)]
    unknown = target != "action" and (m["lagged"] or
              (target == "action_linked_consequence" and not m["provenance"]))
    if unknown:
        return {"factual_bad": None, "effects": [None] * n, "shapley": None,
                "endpoint": None, "latest": None, "changed": [None] * n,
                "coalitions": [None] * (1 << n), "valid": valid}
    bad = target != "action" and m["retry"] and not m["idempotent"]
    fresh = q if target != "action" and not m["idempotent"] else 0.0
    changed = [fresh, fresh] + ([float(bad)] if n == 3 else [])
    effects = [rate - int(bad) for rate in changed]
    coalitions = [None if valid[mask] < 1 else (float(bad) if mask & 2 else fresh)
                  for mask in range(1 << n)]
    defined = all(value is not None for value in coalitions)
    shares = ([0.0, coalitions[2] - coalitions[0]] + ([0.0] if n == 3 else [])) if defined else None
    return {"factual_bad": bad, "effects": effects, "shapley": shares,
            "endpoint": float(bad) - fresh, "latest": max(
                (i for i, value in enumerate(effects) if value < 0), default=None),
            "changed": changed, "coalitions": coalitions, "valid": valid}


def expected_outcome(name, reached):
    m = mechanism(name)
    checked(reached in (2, 3), name + ": completed refund trajectory must reach 2 or 3 decisions")
    state = None if m["lagged"] else not (reached == 3 and not m["idempotent"])
    linked = state if state is False or m["provenance"] else None
    return {"action": True, "consequence": state, "action_linked_consequence": linked}


def wilson(k, n, confidence):
    if n == 0:
        return {"numerator": 0, "denominator": 0, "rate": None, "confidence_interval": None,
                "confidence": confidence, "interval_method": "Wilson score"}
    checked(0 <= k <= n, "Wilson numerator in denominator")
    z = -NormalDist().inv_cdf((1 - confidence) / 2)
    p = k / n
    denominator = n + z * z
    center = (k + z * z / 2) / denominator
    half = z * math.sqrt(n * p * (1 - p) + z * z / 4) / denominator
    return {"numerator": k, "denominator": n, "rate": p,
            "confidence_interval": [0.0 if k == 0 else max(0.0, center - half),
                                    1.0 if k == n else min(1.0, center + half)],
            "confidence": confidence, "interval_method": "Wilson score"}


def numeric(observations, reference, confidence):
    intervals = [ci for _, ci in observations if ci is not None]
    errors = [value - reference for value, _ in observations] if reference is not None else []
    scored_intervals = intervals if reference is not None else []
    included = sum(lo <= reference <= hi for lo, hi in scored_intervals)
    bias = mean(errors) if errors else None
    squared = [error * error for error in errors]
    rmse = math.sqrt(mean(squared)) if squared else None
    bias_se = math.sqrt(variance(errors) / len(errors)) if len(errors) >= 2 else None
    rmse_se = (math.sqrt(variance(squared) / len(squared)) / (2 * rmse)
               if len(squared) >= 2 and rmse else None)
    degenerate = sum(lo == hi for lo, hi in intervals)
    return {"reference": reference, "scored_estimates": len(errors), "bias": bias,
            "bias_mcse": bias_se, "rmse": rmse, "rmse_mcse": rmse_se,
            "interval_coverage": wilson(included, len(scored_intervals), confidence),
            "available_estimates": len(observations), "available_intervals": len(intervals),
            "degenerate_intervals": degenerate,
            "degenerate_interval_rate": wilson(degenerate, len(intervals), confidence)}


def percentile(ordered, probability):
    position = probability * (len(ordered) - 1)
    floor = int(position)
    fraction = position - floor
    return ordered[floor] + fraction * (ordered[min(floor + 1, len(ordered) - 1)] - ordered[floor])


def bootstrap(bad_values, factual_bad, plan, seed):
    key = (tuple(bad_values), factual_bad, seed)
    if key not in BOOTSTRAP_CACHE:
        if min(bad_values) == max(bad_values):
            point = float(bad_values[0]) - int(factual_bad)
            answer = [point, point]
        else:
            rng = random.Random(seed)
            count = len(bad_values)
            draws = sorted(sum(bad_values[rng.randrange(count)] for _ in range(count)) / count
                           - int(factual_bad) for _ in range(plan["bootstrap_samples"]))
            alpha = (1 - plan["confidence"]) / 2
            answer = [percentile(draws, alpha), percentile(draws, 1 - alpha)]
        BOOTSTRAP_CACHE[key] = answer
    return BOOTSTRAP_CACHE[key]


def normal_ci(values, confidence):
    center = mean(values)
    width = -NormalDist().inv_cdf((1 - confidence) / 2) * math.sqrt(variance(values) / len(values))
    return [center - width, center + width]


def exact_normal_behavior(q, plan):
    """Enumerate the finite pair law; independent of any observed trial results."""
    if plan["samples_per_eval"] != 1:
        return {"available": False, "reason": "trinomial enumeration is restricted to one draw per coalition occurrence"}
    pairs = plan["pairs"]
    answers = []
    laws = (([-0.5, 0.0, 0.5], [q * (1 - q), 1 - 2 * q * (1 - q), q * (1 - q)], 0.0),
            ([-1.0, -0.5, 0.0], [q * q, 2 * q * (1 - q), (1 - q)**2], -q))
    for values, probabilities, reference in laws:
        included, mass = 0.0, 0.0
        for first in range(pairs + 1):
            for second in range(pairs - first + 1):
                third = pairs - first - second
                probability = (math.comb(pairs, first) * math.comb(pairs - first, second)
                    * probabilities[0]**first * probabilities[1]**second * probabilities[2]**third)
                ci = normal_ci([values[0]] * first + [values[1]] * second + [values[2]] * third,
                               plan["confidence"])
                included += probability * (ci[0] <= reference <= ci[1])
                mass += probability
        checked(math.isclose(mass, 1.0, abs_tol=1e-12), "trinomial pair-law mass")
        answers.append(included)
    endpoint = 0.0
    count = plan["endpoint_samples"]
    for bad in range(count + 1):
        probability = math.comb(count, bad) * q**bad * (1 - q)**(count - bad)
        ci = normal_ci([1.0] * bad + [0.0] * (count - bad), plan["confidence"])
        endpoint += probability * (ci[0] <= q <= ci[1])
    return {"available": True, "retry_probability": q, "pairs": pairs,
            "samples_per_coalition": 1, "endpoint_samples": count,
            "confidence": plan["confidence"],
            "irrelevant_selection_false_nonzero_probability": 1 - answers[0],
            "protective_stop_coefficient_interval_coverage": answers[1],
            "independent_endpoint_interval_coverage": endpoint,
            "meaning": "exact finite multinomial/binomial enumeration under ideal independent Bernoulli draws; no observed outcomes used"}


def branch_label(branch, target):
    if branch["status"] != "completed":
        return branch["status"]
    return "unknown" if branch["target_values"][target] is None else "known"


def coverage(labels):
    counts = Counter(labels)
    return {"planned": len(labels), **{name: counts[name] for name in
            ("known", "unknown", "invalid", "failed", "unstarted")}}


def failure_reason(method, result, factual_bad=None):
    if result is None:
        return "method_failure"
    if method == "contrastive" and factual_bad is None:
        return "unknown_factual"
    for label in ("unstarted", "failed", "invalid", "unknown"):
        if result[label]:
            return label
    return "unavailable"


def verify_trial(record, plan, schedule):
    compare(record["seed_plan"], schedule, "trial seed plan")
    name, n = schedule["mechanism"], schedule["decision_count"]
    facts = record["factual"]
    for method in ("contrastive", "shapley"):
        fact = facts[method]
        compare(fact["status"], "completed", method + " factual capture")
        compare(fact["calls"], n, method + " factual calls")
        compare(len(fact["decisions"]), n, method + " factual receipt count")
        for target in TARGETS:
            expected_bad = truth(name, target)["factual_bad"]
            compare(fact["targets"][FIELDS[target]], None if expected_bad is None else not expected_bad,
                    method + "/factual/" + target)
    compare(facts["contrastive"]["trace_sha256"], facts["shapley"]["trace_sha256"], "paired factual hash")
    compare(record["errors"], [], "trial operation errors")
    out = {"contrastive": {}, "shapley": {}, "endpoints": {}, "loci": {}}
    for method in ("contrastive", "shapley"):
        receipt = record[method]
        checked(receipt is not None, "replayer result exists")
        branches = receipt["branches"]
        compare(len(branches), schedule[method + "_branches"], method + " all branches retained")
        for branch in branches:
            compare(branch["policy_calls"], sum(d["policy_calls"] for d in branch["reached_decisions"]),
                    method + " reached call sum")
            if branch["status"] == "completed":
                compare(branch["target_values"], {target: expected_outcome(name, len(branch["reached_decisions"]))[target]
                                                for target in plan["targets"]}, method + " allowed outcome")
            else:
                compare(branch["target_values"], None, method + " incomplete has no target")
            for decision in branch["reached_decisions"]:
                if decision["source"] == "held_factual":
                    compare(decision["policy_calls"], 0, method + " held calls")
        continuation = sum(branch["policy_calls"] for branch in branches)
        compare(record["calls"][method], continuation, method + " actual continuation calls")
        checked(n + continuation <= schedule["max_calls"], method + " shared budget bound")
        compare(receipt["summary"]["shared_budget_calls_before"], n, method + " shared initial count")
        compare(receipt["summary"]["shared_budget_calls_after"], n + continuation, method + " shared final count")
    compare(record["calls"]["factual"], 2 * n, "both factual captures counted")
    compare(record["calls"]["total"], 2 * n + record["calls"]["contrastive"] + record["calls"]["shapley"],
            "total actual calls")
    ctr = record["contrastive"]
    for position in range(n):
        samples = ctr["branches"][position * plan["samples"]:(position + 1) * plan["samples"]]
        for offset, branch in enumerate(samples):
            compare({k: branch[k] for k in ("index", "decision_index", "continuation_seed")},
                    {"index": position * plan["samples"] + offset, "decision_index": position,
                     "continuation_seed": schedule["contrastive_seed"] + position * plan["samples"] + offset},
                    "contrastive branch keys")
        for target in plan["targets"]:
            counts = coverage([branch_label(b, target) for b in samples])
            factual_bad = truth(name, target)["factual_bad"]
            available = factual_bad is not None and counts["known"] == plan["samples"]
            values = [not b["target_values"][target] for b in samples if branch_label(b, target) == "known"]
            rate = mean(values) if available else None
            effect = rate - int(factual_bad) if available else None
            ci = bootstrap(values, factual_bad, plan, schedule["bootstrap_seed"]) if available else None
            rescue = effect < 0 and ci[1] < 0 if available else None
            expected = {"decision_index": position, "target": target,
                        "status": "estimated" if available else "refused", "factual_bad": factual_bad,
                        "changed_bad_rate": rate, "effect": effect, "confidence_interval": ci,
                        "significant_rescue": rescue, "interval_degenerate": ci[0] == ci[1] if ci else None,
                        **{f"{label}_samples": counts[label] for label in ("known", "unknown", "failed", "unstarted")}}
            actual = next(row for row in ctr["results"] if row["target"] == target and row["decision_index"] == position)
            compare(actual, expected, "contrastive estimate")
            out["contrastive"][target, position] = {**expected, "counts": counts,
                "reason_label": failure_reason("contrastive", counts, factual_bad) if not available else None}
    for target in plan["targets"]:
        entries = [out["contrastive"][target, position] for position in range(n)]
        rescues = [row["decision_index"] for row in entries if row["significant_rescue"]]
        status = "refused" if any(row["status"] == "refused" for row in entries) else (
            "identified" if rescues else "no_rescue")
        locus = {"target": target, "status": status,
                 "decision_index": max(rescues) if status == "identified" else None}
        compare(next(row for row in ctr["loci"] if row["target"] == target), locus, "contrastive locus")
        out["loci"][target] = locus
    shp = record["shapley"]
    rng = random.Random(schedule["permutation_seed"])
    permutations = []
    expected_slots = []
    def slot(role, pair, walk, step, held, sample):
        index = len(expected_slots)
        expected_slots.append({"index": index, "role": role, "pair_index": pair, "walk": walk,
            "step": step, "held_indices": sorted(held), "sample_index": sample,
            "continuation_seed": schedule["shapley_seed"] + index})
    for role, held in (("endpoint_empty", []), ("endpoint_full", list(range(n)))):
        for sample in range(plan["endpoint_samples"]):
            slot(role, None, None, None, held, sample)
    for pair in range(plan["pairs"]):
        order = list(range(n))
        rng.shuffle(order)
        permutations.append(order)
        for walk, order_in_walk in (("forward", order), ("reverse", order[::-1])):
            for step in range(n + 1):
                for sample in range(plan["samples_per_eval"]):
                    slot("walk", pair, walk, step, order_in_walk[:step], sample)
    compare(shp["permutations"], permutations, "permutation schedule")
    compare(shp["slots"], expected_slots, "complete coalition schedule")
    for index, branch in enumerate(shp["branches"]):
        compare(branch["slot_index"], index, "coalition branch index")
    for target in plan["targets"]:
        labels = [branch_label(branch, target) for branch in shp["branches"]]
        path_indices = [slot["index"] for slot in expected_slots if slot["role"] == "walk"]
        path_coverage = coverage([labels[i] for i in path_indices])
        vectors, pair_labels = [], []
        for pair, order in enumerate(permutations):
            indices = [slot["index"] for slot in expected_slots if slot["role"] == "walk" and slot["pair_index"] == pair]
            counts = coverage([labels[i] for i in indices])
            label = next((label for label in ("unstarted", "failed", "invalid", "unknown") if counts[label]), "known")
            pair_labels.append(label)
            if label != "known":
                vectors.append(None)
                continue
            vector = [0.0] * n
            for walk, walk_order in (("forward", order), ("reverse", order[::-1])):
                coalition_means = []
                for step in range(n + 1):
                    indices = [slot["index"] for slot in expected_slots if slot["role"] == "walk"
                               and slot["pair_index"] == pair and slot["walk"] == walk and slot["step"] == step]
                    coalition_means.append(mean(not shp["branches"][i]["target_values"][target] for i in indices))
                for step, position in enumerate(walk_order):
                    vector[position] += (coalition_means[step + 1] - coalition_means[step]) / 2
            vectors.append(vector)
        pair_counts = coverage(pair_labels)
        available = pair_counts["known"] == plan["pairs"]
        for position in range(n):
            values = [vector[position] if vector is not None else None for vector in vectors]
            point = mean(values) if available else None
            ci = normal_ci(values, plan["confidence"]) if available else None
            expected = {"decision_index": position, "target": target,
                        "status": "estimated" if available else "refused", "shapley_value": point,
                        "confidence_interval": ci, "pair_values": values, "coverage": path_coverage,
                        "interval_degenerate": ci[0] == ci[1] if ci else None,
                        **{f"{label}_pairs": pair_counts[label] for label in ("known", "unknown", "invalid", "failed", "unstarted")}}
            actual = next(row for row in shp["results"] if row["target"] == target and row["decision_index"] == position)
            compare(actual, expected, "Shapley estimate")
            out["shapley"][target, position] = {**expected, "counts": pair_counts,
                "reason_label": failure_reason("shapley", pair_counts) if not available else None}
        ep_counts, ep_values = [], []
        for role in ("endpoint_empty", "endpoint_full"):
            indices = [slot["index"] for slot in expected_slots if slot["role"] == role]
            ep_counts.append(coverage([labels[i] for i in indices]))
            ep_values.append([not shp["branches"][i]["target_values"][target] for i in indices if labels[i] == "known"])
        ep_available = all(counts["known"] == plan["endpoint_samples"] for counts in ep_counts)
        empty, full = (mean(values) for values in ep_values) if ep_available else (None, None)
        difference = full - empty if ep_available else None
        ep_ci = None
        if ep_available:
            width = -NormalDist().inv_cdf((1 - plan["confidence"]) / 2) * math.sqrt(
                sum(variance(values) for values in ep_values) / plan["endpoint_samples"])
            ep_ci = [difference - width, difference + width]
        coefficient_sum = sum(out["shapley"][target, i]["shapley_value"] for i in range(n)) if available else None
        discrepancy = coefficient_sum - difference if available and ep_available else None
        expected = {"target": target, "status": "estimated" if ep_available else "refused",
            "empty_bad_rate": empty, "full_bad_rate": full, "endpoint_difference": difference,
            "confidence_interval": ep_ci, "empty_coverage": ep_counts[0], "full_coverage": ep_counts[1],
            "coefficient_sum": coefficient_sum, "discrepancy": discrepancy}
        compare(next(row for row in shp["endpoint_checks"] if row["target"] == target), expected, "independent endpoints")
        merged_counts = {label: sum(counts[label] for counts in ep_counts) for label in ep_counts[0]}
        out["endpoints"][target] = {**expected,
            "reason_label": failure_reason("shapley", merged_counts) if not ep_available else None}
    return out


def audit(root, expected_source):
    started = time.monotonic()
    protocol, manifest, summary = load(root / "protocol.json"), load(root / "manifest.json"), load(root / "summary.json")
    compare(manifest["status"], "completed", "export completion")
    if expected_source:
        compare(protocol["source_revision"], expected_source, "declared source revision")
    for artifact in manifest["artifacts"]:
        payload = (root / artifact["path"]).read_bytes()
        compare(len(payload), artifact["bytes"], "manifest artifact size")
        compare(hashlib.sha256(payload).hexdigest(), artifact["sha256"], "manifest artifact hash")
    plan = protocol["plan"]
    schedules = protocol["trial_schedule"]
    cursor = plan["seed"]
    total = sum((1 + mechanism(name)["n"] * plan["samples"] + 2 * plan["endpoint_samples"]
                 + 2 * plan["pairs"] * (mechanism(name)["n"] + 1) * plan["samples_per_eval"])
                * plan["repeats"] for name in plan["mechanisms"])
    inference_start = 6 * (plan["seed"] + total - 1) + 6
    calculated_schedule = []
    for name in plan["mechanisms"]:
        n = mechanism(name)["n"]
        for rep in range(plan["repeats"]):
            index = len(calculated_schedule)
            c_count = n * plan["samples"]
            s_count = 2 * plan["endpoint_samples"] + 2 * plan["pairs"] * (n + 1) * plan["samples_per_eval"]
            calculated_schedule.append({"index": index, "mechanism": name, "replicate": rep,
                "decision_count": n, "factual_seed": cursor, "contrastive_seed": cursor + 1,
                "contrastive_branches": c_count, "shapley_seed": cursor + 1 + c_count,
                "shapley_branches": s_count, "permutation_seed": inference_start + 2 * index,
                "bootstrap_seed": inference_start + 2 * index + 1,
                "max_calls": 3 if mechanism(name)["budget"] else plan["max_calls"]})
            cursor += 1 + c_count + s_count
    compare(schedules, calculated_schedule, "global independent schedule")
    compare(protocol["planned_trials"], len(schedules), "planned trial count")
    compare(protocol["retention"]["full_evidence_replicates"], [0], "predeclared evidence selection")
    for name in plan["mechanisms"]:
        for target in plan["targets"]:
            independent = truth(name, target)
            recorded = protocol["evaluator_analytic_references"][name]["targets"][target]
            compare(recorded, {"factual_bad": independent["factual_bad"],
                "changed_bad_rates": independent["changed"], "contrastive_effects": independent["effects"],
                "shapley_values": independent["shapley"], "endpoint_difference": independent["endpoint"],
                "latest_population_rescue": independent["latest"], "coalition_bad_rates": independent["coalitions"]},
                "independent analytic reference")
    totals = Counter()
    branch_count = 0
    findings = []
    for name in plan["mechanisms"]:
        records, computed = [], []
        with gzip.open(root / "trials" / (name + ".jsonl.gz"), "rt", encoding="utf-8") as stream:
            for line in stream:
                record = decode(line)
                schedule = schedules[len(records) + plan["mechanisms"].index(name) * plan["repeats"]]
                computed.append(verify_trial(record, plan, schedule))
                records.append(record)
                for field in ("factual", "contrastive", "shapley", "total"):
                    totals[field] += record["calls"][field]
                branch_count += schedule["contrastive_branches"] + schedule["shapley_branches"]
        compare(len(records), plan["repeats"], "all repetitions retained for " + name)
        for method in ("contrastive", "shapley"):
            statuses = Counter()
            outcomes = {target: Counter() for target in plan["targets"]}
            errors = Counter()
            for record in records:
                for branch in record[method]["branches"]:
                    statuses[branch["status"]] += 1
                    if branch["error_type"]:
                        errors[branch["error_type"]] += 1
                    if branch["status"] == "completed":
                        for target in plan["targets"]:
                            outcomes[target]["unknown" if branch["target_values"][target] is None else "known"] += 1
            row = next(row for row in summary["branches"] if row["mechanism"] == name and row["method"] == method)
            compare(row, {"planned_branches": sum(statuses.values()),
                "status_counts": {key: statuses[key] for key in ("completed", "invalid", "failed", "unstarted")},
                "completed_target_outcomes": {target: {key: outcomes[target][key] for key in ("known", "unknown")}
                                              for target in plan["targets"]},
                "error_type_counts": dict(errors)}, "aggregate branch coverage")
            if method == "shapley":
                m = mechanism(name)
                exponents = [plan["samples_per_eval"] * sum(abs(order.index(1) - order.index(2))
                                for order in record["shapley"]["permutations"]) if m["retry"] else 0
                             for record in records]
                availability = ((2 * m["q"]**plan["samples_per_eval"]
                                 + m["q"]**(2 * plan["samples_per_eval"])) / 3)**plan["pairs"] if m["retry"] else 1.0
                compare(row["nominal_structural_path_availability"], {"probability": availability,
                        "given_permutations": [m["q"]**exponent for exponent in exponents]},
                        "independent structural availability")
        for target in plan["targets"]:
            t = truth(name, target)
            for method in ("contrastive", "shapley"):
                references = t["effects"] if method == "contrastive" else t["shapley"]
                for position in range(mechanism(name)["n"]):
                    estimates = [trial[method][target, position] for trial in computed]
                    estimated = [row for row in estimates if row["status"] == "estimated"]
                    reference = references[position] if references is not None else None
                    observations = [(row["effect" if method == "contrastive" else "shapley_value"], row["confidence_interval"])
                                    for row in estimated]
                    metrics = numeric(observations, reference, plan["confidence"])
                    n = len(records)
                    exclusions = sum(ci[0] > 0 or ci[1] < 0 for _, ci in observations if ci is not None) if reference == 0 else 0
                    expected = {"planned_trials": n, "estimated_trials": len(estimated),
                        "refused_trials": n - len(estimated), "reference_eligible_trials": n if reference is not None else 0,
                        "reference_ineligible_trials": 0 if reference is not None else n,
                        "refusal_reason_counts": dict(Counter(row["reason_label"] for row in estimates if row["status"] != "estimated")),
                        "availability_rate": wilson(len(estimated), n, plan["confidence"]),
                        "refusal_rate": wilson(n - len(estimated), n, plan["confidence"]), **metrics,
                        "eligible_unscored_trials": (n if reference is not None else 0) - metrics["scored_estimates"],
                        "analytic_null_position": reference == 0,
                        "zero_reference_interval_exclusion": wilson(exclusions, len(observations) if reference == 0 else 0, plan["confidence"]),
                        "false_distractor_flags": exclusions if reference == 0 else None,
                        "interval_coverage_including_refusals": wilson(metrics["interval_coverage"]["numerator"], n if reference is not None else 0, plan["confidence"])}
                    actual = next(row for row in summary["estimates"] if row["mechanism"] == name and row["method"] == method
                                  and row["target"] == target and row["decision_index"] == position)
                    compare(actual, expected, "aggregate estimate scores")
                    if target == "consequence" and method == "contrastive" and position == 1 or (
                            target == "consequence" and method == "shapley" and name.startswith("protective-stop")):
                        findings.append({"mechanism": name, "method": method, "target": target, "position": position,
                            "truth": reference, "coverage": metrics["interval_coverage"],
                            "bias": metrics["bias"], "rmse": metrics["rmse"],
                            "false_nonzero_flags": exclusions if reference == 0 else None})
            ep_rows = [trial["endpoints"][target] for trial in computed]
            ep_observations = [(row["endpoint_difference"], row["confidence_interval"])
                               for row in ep_rows if row["status"] == "estimated"]
            ep_metrics = numeric(ep_observations, t["endpoint"], plan["confidence"])
            n, available = len(records), len(ep_observations)
            sums = [(row["coefficient_sum"], None) for row in ep_rows if row["coefficient_sum"] is not None]
            residuals = [row["discrepancy"] for row in ep_rows if row["discrepancy"] is not None]
            ep_expected = {"planned_trials": n, "estimated_trials": available, "refused_trials": n - available,
                "reference_eligible_trials": n if t["endpoint"] is not None else 0,
                "reference_ineligible_trials": 0 if t["endpoint"] is not None else n,
                "refusal_reason_counts": dict(Counter(row["reason_label"] for row in ep_rows if row["status"] != "estimated")),
                "availability_rate": wilson(available, n, plan["confidence"]),
                "refusal_rate": wilson(n - available, n, plan["confidence"]), **ep_metrics,
                "coefficient_sum": numeric(sums, t["endpoint"] if t["shapley"] is not None else None, plan["confidence"]),
                "eligible_unscored_trials": (n if t["endpoint"] is not None else 0) - ep_metrics["scored_estimates"],
                "interval_coverage_including_refusals": wilson(ep_metrics["interval_coverage"]["numerator"], n if t["endpoint"] is not None else 0, plan["confidence"]),
                "efficiency_residual": {"available_trials": len(residuals),
                    "mean": mean(residuals) if residuals else None,
                    "root_mean_square": math.sqrt(mean(value * value for value in residuals)) if residuals else None,
                    "confidence_interval": None}}
            compare(next(row for row in summary["endpoints"] if row["mechanism"] == name and row["target"] == target),
                    ep_expected, "aggregate independent endpoint scores")
            selection = Counter()
            for trial in computed:
                locus = trial["loci"][target]
                key = str(locus["decision_index"]) if locus["status"] == "identified" else locus["status"]
                selection[key] += 1
            eligible = all(value is not None for value in t["effects"])
            match_key = str(t["latest"]) if t["latest"] is not None else "no_rescue"
            matches = selection[match_key] if eligible else 0
            locus_expected = {"planned_trials": n, "reference_eligible_trials": n if eligible else 0,
                "latest_population_rescue": t["latest"],
                "selection_counts": {key: selection[key] for key in ["refused", "no_rescue"] + [str(i) for i in range(mechanism(name)["n"])]},
                "population_rule_match_including_refusals": wilson(matches, n if eligible else 0, plan["confidence"]),
                "population_rule_match_given_available": wilson(matches, n - selection["refused"] if eligible else 0, plan["confidence"])}
            compare(next(row for row in summary["loci"] if row["mechanism"] == name and row["target"] == target),
                    locus_expected, "aggregate nominal locus recovery")
        print("Audited", name, len(records), "predeclared repetitions", flush=True)
    compare(summary["planned_trials"], len(schedules), "summary planned count")
    compare(summary["retained_trials"], len(schedules), "summary retained count")
    compare(summary["factual_failures"], 0, "summary factual failures")
    compare(summary["paired_factual_disagreements"], 0, "summary paired capture agreement")
    compare(summary["actual_policy_calls"], dict(totals), "aggregate actual calls")
    return {"audit_passed": True, "auditor": "independent standard-library numerical and mechanism audit",
        "auditor_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "production_analyzer_imported": False, "production_analytic_reference_imported": False,
        "source_revision": protocol["source_revision"], "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "trial_count": len(schedules), "all_planned_branch_receipts": branch_count,
        "manifest_artifacts_checked": len(manifest["artifacts"]), "assertions": CHECKS,
        "actual_policy_calls": dict(totals), "model_calls": 0, "redraws": 0,
        "checks": ["independently derived analytic refund truth and coalition availability",
            "all declared trial, phase and inference seed ranges", "paired factual captures and actual call budgets",
            "all branch outcomes from reached decision lengths and mechanism evidence rules",
            "contrastive bad rates, bootstrap intervals, refusals and latest nominal rescue loci",
            "Shapley forward/reverse walk marginals, pair values, sample variance and normal intervals",
            "independent endpoint estimates, normal intervals and descriptive discrepancy",
            "every score/refusal/eligibility denominator and Wilson interval",
            "bias, RMSE, Monte Carlo uncertainty, zero-width and null-flag rates",
            "conditional and marginal positional structural availability"],
        "scientific_findings": findings,
        "analytic_bootstrap_coverage_ceilings": [
            {"mechanism": name, "samples_per_position": plan["samples"],
             "retry_probability": mechanism(name)["q"],
             "coverage_ceiling": 1 - mechanism(name)["q"]**plan["samples"]
                                 - (1 - mechanism(name)["q"])**plan["samples"],
             "reason": "All-zero or all-one Bernoulli samples produce a constant bootstrap interval that excludes interior probability truth.",
             "scope": "stochastic prefix positions 0 and 1; consequence and linked consequence"}
            for name in plan["mechanisms"] if name.startswith(("protective-stop", "retry-pivot"))],
        "analytic_normal_interval_behavior": [
            {"mechanism": name, **exact_normal_behavior(mechanism(name)["q"], plan)}
            for name in plan["mechanisms"] if name.startswith("protective-stop")],
        "limits": ["Audit confirms exported calculations, not nominal coverage or true RNG independence.",
            "Full public traces are retained for predeclared replicate 0; other repetitions retain compact receipts.",
            "Refund policy uses a declared factual intervention; these are conditional synthetic mechanisms.",
            "State and linked targets share outcomes and cannot count as independent samples.",
            "Undefined retry coalition games have no fabricated Shapley population values.",
            "Synthetic interval behavior cannot establish model accuracy, interaction recovery or superiority."],
        "elapsed_seconds": time.monotonic() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-source")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.root, args.expected_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("audit_passed", "trial_count", "assertions", "elapsed_seconds")}), flush=True)


if __name__ == "__main__":
    main()
