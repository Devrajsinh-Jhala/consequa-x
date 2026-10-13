"""Independent SciPy/reference audit of saved same-draw interval comparisons.

Install scipy in a separate audit environment; it is not a runtime dependency.
The original standard-library auditor independently reconstructs all raw draws,
walk vectors, old intervals, budgets, seeds and mechanism truth. This extension
checks new intervals and aggregate metrics without the production analyzer.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import platform

import scipy
from scipy.stats import beta, binom


REPOSITORY = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "frozen_statistics_auditor",
    REPOSITORY/"output/calibration-probe-2026-10-11/audits/audit_statistics.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def exact(k, n, tail):
    return (0. if k == 0 else float(beta.ppf(tail, k, n-k+1)),
            1. if k == n else float(beta.isf(tail, k+1, n-k)))


def numeric(observations, truth, confidence):
    answer = reference.numeric(observations, truth, confidence)
    intervals = [ci for _, ci in observations if ci is not None]
    answer["mean_interval_width"] = (sum(hi-lo for lo, hi in intervals)/len(intervals)
                                      if intervals else None)
    eligible = truth is not None and truth != 0
    successes = (sum(lo > 0 if truth > 0 else hi < 0 for lo, hi in intervals)
                 if eligible else 0)
    answer["reference_sign_detection"] = reference.wilson(
        successes, len(intervals) if eligible else 0, confidence)
    return answer


def audit_math():
    # This mode directly checks the public numeric implementation against SciPy.
    # The saved replay mode below does not import the production analyzer.
    import sys
    sys.path.insert(0, str(REPOSITORY/"src"))
    from consequa_x.benchmark.intervals import binomial_interval, binomial_difference_interval

    maximum_error, cases = 0., 0
    for n in (1, 2, 8, 16, 20, 32, 64, 100, 1000):
        counts = range(n+1) if n <= 100 else (0, 1, 10, 500, 990, 999, 1000)
        for confidence in (.5, .9, .95, .99, math.nextafter(1., 0.)):
            for k in counts:
                calculated = binomial_interval(k, n, confidence=confidence)
                expected = exact(k, n, (1-confidence)/2)
                reference.compare(calculated, expected, "SciPy beta CP inversion")
                maximum_error = max(maximum_error, *(abs(a-b) for a, b in zip(calculated, expected)))
                # Different endpoint counts/sample sizes and both random marginals.
                empty_count, empty_total = (n-k)//2, n+1
                actual_difference = binomial_difference_interval(k, n, empty_count, empty_total,
                                                                 confidence=confidence)
                full, empty = exact(k, n, (1-confidence)/4), exact(empty_count, empty_total, (1-confidence)/4)
                reference.compare(actual_difference, (full[0]-empty[1], full[1]-empty[0]),
                                  "SciPy simultaneous marginal difference")
                cases += 1
    return {"audit_passed": True, "binomial_cases": cases, "difference_cases": cases,
            "maximum_binomial_absolute_error": maximum_error,
            "confidence_levels": [.5, .9, .95, .99, math.nextafter(1., 0.)],
            "python": platform.python_version(), "scipy": scipy.__version__,
            "assertions": reference.CHECKS,
            "reference": "scipy.stats.beta.ppf / isf; upper tails evaluated directly"}


def audit_grid(root):
    finite = reference.load(root/"finite-binomial.json")
    c = finite["confidence"]
    maps = {}
    for block in finite["count_intervals"]:
        n, method = block["samples"], block["method"]
        expected = []
        for k in range(n+1):
            if method == "clopper_pearson":
                expected.append(exact(k, n, (1-c)/2))
            elif method == "wilson":
                expected.append(reference.wilson(k, n, c)["confidence_interval"])
            elif method == "percentile_bootstrap_limit":
                expected.append((float(binom.ppf((1-c)/2, n, k/n))/n,
                                 float(binom.ppf(1-(1-c)/2, n, k/n))/n))
            else:
                raise AssertionError("unrecognized grid method")
        reference.compare(block["intervals_by_success_count"], expected, "finite interval count grid")
        maps[n, method] = block["intervals_by_success_count"]
    reference.checked(len(finite["rows"]) == 132, "complete finite grid")
    for row in finite["rows"]:
        n, q = row["samples"], Fraction(str(row["probability"]))
        intervals = maps[n, row["method"]]
        weights = [math.comb(n, k)*q**k*(1-q)**(n-k) for k in range(n+1)]
        reference.checked(sum(weights) == 1, "rational probability mass")
        covered = sum(w for w, (lo, hi) in zip(weights, intervals) if lo <= float(q) <= hi)
        reference.compare(row["coverage_fraction"], [covered.numerator, covered.denominator], "exact grid coverage")
        reference.compare(row["coverage"], float(covered), "grid coverage float")
        reference.compare(row["expected_width"], sum(float(w)*(hi-lo) for w, (lo, hi) in zip(weights, intervals)), "grid width")
        reference.compare(row["zero_width_probability"], float(sum(w for w, (lo, hi) in zip(weights, intervals) if lo == hi)), "grid collapse")
    return {name: min(r["coverage"] for r in finite["rows"] if r["method"] == name)
            for name in ("percentile_bootstrap_limit", "wilson", "clopper_pearson")}


def unchanged(before, after, omitted, label):
    reference.compare({k: v for k, v in after.items() if k not in omitted},
                      {k: v for k, v in before.items() if k not in omitted}, label)


def check_summary(rows, results, name, method, plan):
    n, c = plan["repeats"], plan["confidence"]
    for row in rows:
        if row["mechanism"] != name:
            continue
        target = row["target"]
        position = row.get("decision_index")
        t = reference.truth(name, target)
        truth = (t["effects"][position] if method == "contrastive" else
                 t["shapley"][position] if method == "shapley" and t["shapley"] is not None else
                 t["endpoint"] if method == "endpoint" else None)
        selected = [next(item for item in trial if item["target"] == target
                         and (position is None or item["decision_index"] == position)) for trial in results]
        available = [item for item in selected if item["status"] == "estimated"]
        field = {"contrastive": "effect", "shapley": "shapley_value", "endpoint": "endpoint_difference"}[method]
        observations = [(item[field], item["confidence_interval"]) for item in available]
        metrics = numeric(observations, truth, c)
        reference.compare(row, {"planned_trials": n, "estimated_trials": len(available),
            "refused_trials": n-len(available), "reference_eligible_trials": n if truth is not None else 0,
            "reference_ineligible_trials": n if truth is None else 0, **metrics,
            "availability_rate": reference.wilson(len(available), n, c),
            "interval_coverage_including_refusals": reference.wilson(metrics["interval_coverage"]["numerator"], n if truth is not None else 0, c)},
            "new method aggregate coverage / width / sign / errors / refusal eligibility")
        if method != "endpoint":
            exclusions = sum(lo > 0 or hi < 0 for _, (lo, hi) in observations) if truth == 0 else 0
            reference.compare(row["zero_reference_interval_exclusion"], reference.wilson(exclusions, len(available) if truth == 0 else 0, c), "null flags")


def audit(root, expected_source):
    root = root.resolve()
    protocol, summary = reference.load(root/"protocol.json"), reference.load(root/"summary.json")
    # Reuse frozen auditor code, without modifying any old retained report.
    raw_audit = reference.audit(root/"raw", expected_source)
    reference.compare(protocol["source_revision"], expected_source, "comparison frozen source")
    grid = audit_grid(root)
    plan, c = protocol["plan"], protocol["plan"]["confidence"]
    totals, comparison_count = Counter(), 0
    for name in plan["mechanisms"]:
        raw_path, compared_path = root/"raw/trials"/(name+".jsonl.gz"), root/"comparisons"/(name+".jsonl.gz")
        import gzip
        with gzip.open(raw_path, "rt", encoding="utf-8") as stream:
            raw = [reference.decode(line) for line in stream]
        with gzip.open(compared_path, "rt", encoding="utf-8") as stream:
            compared = [reference.decode(line) for line in stream]
        reference.checked(len(raw) == len(compared) == plan["repeats"], "same trial schedule")
        variants = {"contrastive": {k: [] for k in summary["contrastive"]},
                    "shapley": {k: [] for k in summary["shapley"]},
                    "endpoint": {k: [] for k in summary["shapley"]}}
        for before, after in zip(raw, compared):
            reference.compare(set(after["contrastive"]), {"percentile_bootstrap", "wilson", "clopper_pearson"}, "complete contrastive variants")
            reference.compare(set(after["shapley"]), {"normal", "hoeffding_exact_endpoints"}, "complete pair variants")
            reference.compare(after["seed_plan"], before["seed_plan"], "same keys")
            reference.compare(after["calls"], before["calls"], "same actual budget calls")
            reference.compare(after["additional_policy_calls"], 0, "no comparison model calls")
            for field, value in before["calls"].items():
                totals[field] += value
            for method, records in after["contrastive"].items():
                reference.compare(len(records["results"]), len(before["contrastive"]["results"]), "every contrastive result retained")
                variants["contrastive"][method].append(records["results"])
                reference.compare(records["summary"]["policy_calls"], before["contrastive"]["summary"]["policy_calls"], "unchanged contrastive calls")
                for old, new in zip(before["contrastive"]["results"], records["results"]):
                    unchanged(old, new, ("confidence_interval", "interval_degenerate", "significant_rescue"), "same contrastive sample receipt")
                    if old["status"] == "refused":
                        reference.compare(new, old, "original refusal preserved")
                        continue
                    branches = [b for b in before["contrastive"]["branches"] if b["decision_index"] == old["decision_index"]]
                    k = sum(not b["target_values"][old["target"]] for b in branches)
                    if method == "percentile_bootstrap":
                        ci = old["confidence_interval"]
                    elif method == "wilson":
                        ci = reference.wilson(k, len(branches), c)["confidence_interval"]
                        ci = [v-int(old["factual_bad"]) for v in ci]
                    else:
                        ci = [v-int(old["factual_bad"]) for v in exact(k, len(branches), (1-c)/2)]
                    reference.compare(new["confidence_interval"], ci, "new contrastive numeric bound")
                    reference.compare(new["interval_degenerate"], ci[0] == ci[1], "new collapse flag")
                    reference.compare(new["significant_rescue"], new["effect"] < 0 and ci[1] < 0, "nominal rescue criterion")
                for locus in records["loci"]:
                    items = [r for r in records["results"] if r["target"] == locus["target"]]
                    candidates = [r["decision_index"] for r in items if r["significant_rescue"]]
                    status = "refused" if any(r["status"] == "refused" for r in items) else "identified" if candidates else "no_rescue"
                    reference.compare(locus["status"], status, "unchanged latest rule")
                    reference.compare(locus["decision_index"], max(candidates) if status == "identified" else None, "latest selected index")
            for method, records in after["shapley"].items():
                reference.compare(len(records["results"]), len(before["shapley"]["results"]), "every pair result retained")
                reference.compare(len(records["endpoint_checks"]), len(before["shapley"]["endpoint_checks"]), "every endpoint result retained")
                variants["shapley"][method].append(records["results"])
                variants["endpoint"][method].append(records["endpoint_checks"])
                for old, new in zip(before["shapley"]["results"], records["results"]):
                    unchanged(old, new, ("confidence_interval", "interval_degenerate"), "same signed pair vector")
                    if old["status"] == "refused":
                        reference.compare(new, old, "Shapley refusal preserved")
                        continue
                    width = 2*math.sqrt(math.log(2/(1-c))/(2*len(old["pair_values"])))
                    ci = (old["confidence_interval"] if method == "normal" else
                          [max(-1., old["shapley_value"]-width), min(1., old["shapley_value"]+width)])
                    reference.compare(new["confidence_interval"], ci, "bounded independent pair mean")
                for old, new in zip(before["shapley"]["endpoint_checks"], records["endpoint_checks"]):
                    unchanged(old, new, ("confidence_interval",), "same endpoint draws / point / discrepancy")
                    if old["status"] == "refused":
                        reference.compare(new, old, "endpoint refusal preserved")
                        continue
                    counts = {}
                    for role in ("endpoint_full", "endpoint_empty"):
                        ids = {s["index"] for s in before["shapley"]["slots"] if s["role"] == role}
                        draws = [b for b in before["shapley"]["branches"] if b["slot_index"] in ids]
                        counts[role] = sum(not b["target_values"][old["target"]] for b in draws)
                    full = exact(counts["endpoint_full"], plan["endpoint_samples"], (1-c)/4)
                    empty = exact(counts["endpoint_empty"], plan["endpoint_samples"], (1-c)/4)
                    ci = old["confidence_interval"] if method == "normal" else [full[0]-empty[1], full[1]-empty[0]]
                    reference.compare(new["confidence_interval"], ci, "two exact marginal union bound")
            comparison_count += 1
        for method, groups in variants.items():
            for variant, results in groups.items():
                rows = (summary["contrastive"][variant]["estimates"] if method == "contrastive" else
                        summary["shapley"][variant]["endpoints" if method == "endpoint" else "estimates"])
                check_summary(rows, results, name, method, plan)
    reference.compare(summary["actual_policy_calls"], {k: totals[k] for k in ("factual", "contrastive", "shapley", "total")}, "comparison total calls")
    manifest = reference.load(root/"manifest.json")
    for item in manifest["artifacts"]:
        reference.compare(sha256((root/item["path"]).read_bytes()).hexdigest(), item["sha256"], "comparison artifact hash")
    return {"audit_passed": True, "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_revision": expected_source, "python": platform.python_version(), "scipy": scipy.__version__,
            "auditor_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "frozen_raw_auditor": raw_audit, "comparison_trials": comparison_count,
            "assertions": reference.CHECKS, "finite_grid_minimum_coverage": grid,
            "additional_policy_calls": 0, "production_analyzer_imported": False,
            "limits": ["Numerical consistency does not prove live-model independence or calibrated coverage.",
                       "Bootstrap grid is its infinite-resample limit; replay comparison uses finite seeded resamples."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?")
    parser.add_argument("--math-only", action="store_true")
    parser.add_argument("--expected-source")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.math_only and (args.root is None or not args.expected_source):
        parser.error("saved replay audit requires root and --expected-source")
    result = audit_math() if args.math_only else audit(args.root, args.expected_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("audit_passed", "assertions")}))


if __name__ == "__main__":
    main()
