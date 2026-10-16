"""Independent saved-data audit of repeated physical interaction sampling.

No Consequa-X imports, simulator runs or policy calls. The audit reconstructs
seeded decisions, reachability/cost, binomial/normal/bounded intervals, population
references and all aggregates. Full replicate-zero traces additionally use the
saved JSON Schema through the audit-only jsonschema dependency.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import random
from statistics import NormalDist

TARGETS = ("action", "consequence", "action_linked_consequence")
VARIANTS = ("normal", "hoeffding_exact_endpoints")
SPECS = {
    "refund-p50-q50": (0.5, 0.5, False, True, 0, 100),
    "refund-p20-q80": (0.2, 0.8, False, True, 0, 100),
    "refund-p80-q20": (0.8, 0.2, False, True, 0, 100),
    "refund-p100-q100": (1.0, 1.0, False, True, 0, 100),
    "idempotent-p50-q50": (0.5, 0.5, True, True, 0, 100),
    "unknown-provenance-p50-q50": (0.5, 0.5, False, False, 0, 100),
    "lagged-readback-p50-q50": (0.5, 0.5, False, True, 1000, 100),
    "budget-p50-q50": (0.5, 0.5, False, True, 0, 4),
}


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise AssertionError("duplicate JSON key")
        value[key] = item
    return value


def decode(text):
    return json.loads(
        text,
        object_pairs_hook=_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(AssertionError(value)),
    )


@lru_cache(maxsize=4096)
def _cp(k, n, tail):
    """Independent direct finite-binomial inversion, n is small in this study."""

    def mass(p, start, end):
        return math.fsum(math.comb(n, j) * p**j * (1 - p) ** (n - j) for j in range(start, end + 1))

    if k == 0:
        low = 0.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            if mass(mid, k, n) < tail:
                lo = mid
            else:
                hi = mid
        low = (lo + hi) / 2
    if k == n:
        high = 1.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            if mass(mid, 0, k) > tail:
                lo = mid
            else:
                hi = mid
        high = (lo + hi) / 2
    return low, high


def _normal(values, confidence):
    point = sum(values) / len(values)
    variance = sum((value - point) ** 2 for value in values) / (len(values) - 1)
    width = -NormalDist().inv_cdf((1 - confidence) / 2) * math.sqrt(variance / len(values))
    return [point - width, point + width]


def _pair_interval(values, confidence, variant):
    if variant == "normal":
        return _normal(values, confidence)
    point = math.fsum(value / len(values) for value in values)
    width = 2 * math.sqrt(math.log(2 / (1 - confidence)) / (2 * len(values)))
    return [max(-1.0, point - width), min(1.0, point + width)]


def _endpoint_interval(empty, full, confidence, variant):
    difference = sum(full) / len(full) - sum(empty) / len(empty)
    if variant == "normal":

        def variance(v):
            mean = sum(v) / len(v)
            return sum((x - mean) ** 2 for x in v) / (len(v) - 1)

        width = -NormalDist().inv_cdf((1 - confidence) / 2) * math.sqrt(
            variance(empty) / len(empty) + variance(full) / len(full)
        )
        return [difference - width, difference + width]
    low_f, high_f = _cp(sum(full), len(full), (1 - confidence) / 4)
    low_e, high_e = _cp(sum(empty), len(empty), (1 - confidence) / 4)
    return [low_f - high_e, high_f - low_e]


def _rate(k, n, confidence):
    if n == 0:
        return {"numerator": k, "denominator": n, "rate": None, "confidence_interval": None}
    p, z = k / n, -NormalDist().inv_cdf((1 - confidence) / 2)
    scale = 1 + z * z / n
    midpoint = (p + z * z / (2 * n)) / scale
    margin = z / scale * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {
        "numerator": k,
        "denominator": n,
        "rate": p,
        "confidence_interval": [
            0.0 if k == 0 else midpoint - margin,
            1.0 if k == n else midpoint + margin,
        ],
    }


def _metrics(values, reference, repeats, confidence):
    intervals = [bound for _, bound in values if bound is not None]
    errors = [point - reference for point, _ in values] if reference is not None else []
    bias = sum(errors) / len(errors) if errors else None
    return {
        "reference": reference,
        "planned_trials": repeats,
        "available_estimates": len(values),
        "refused_estimates": repeats - len(values),
        "reference_eligible_trials": repeats if reference is not None else 0,
        "reference_eligible_available": len(errors),
        "bias": bias,
        "bias_mcse": math.sqrt(
            sum((error - bias) ** 2 for error in errors) / ((len(errors) - 1) * len(errors))
        )
        if len(errors) > 1
        else None,
        "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)) if errors else None,
        "available_intervals": len(intervals),
        "interval_coverage": _rate(
            sum(low <= reference <= high for low, high in intervals)
            if reference is not None
            else 0,
            len(intervals) if reference is not None else 0,
            confidence,
        ),
        "mean_interval_width": sum(high - low for low, high in intervals) / len(intervals)
        if intervals
        else None,
        "degenerate_intervals": sum(low == high for low, high in intervals),
        "reference_sign_detection": _rate(
            sum(low > 0 if reference > 0 else high < 0 for low, high in intervals)
            if reference not in (None, 0)
            else 0,
            len(intervals) if reference not in (None, 0) else 0,
            confidence,
        ),
        "false_nonzero_flag": _rate(
            sum(low > 0 or high < 0 for low, high in intervals) if reference == 0 else 0,
            len(intervals) if reference == 0 else 0,
            confidence,
        ),
    }


def _reference(spec, game, target):
    p, q, idempotent, provenance, lag, _ = spec
    p, q = Fraction(str(p)), Fraction(str(q))
    rates, unknown, valid = [], [], []
    for mask in range(8):
        s, r = Fraction(1) if mask & 1 else p, Fraction(1) if mask & 2 else q
        legal = (
            Fraction(1)
            if game == "on_reach"
            else s * r
            if mask & 4
            else s
            if mask & 2
            else Fraction(1)
        )
        bad = 1 - s if target == "action" or idempotent else 1 - s * (1 - r)
        missing = (
            Fraction(0)
            if target == "action"
            else Fraction(1)
            if lag
            else (
                (s if idempotent else s * (1 - r))
                if target == "action_linked_consequence" and not provenance
                else Fraction(0)
            )
        )
        rates.append(float(bad) if legal == 1 and missing == 0 else None)
        unknown.append(float(missing))
        valid.append(float(legal))
    eligible = all(value is not None for value in rates)
    if eligible:
        shares = (
            [float(-(1 - p)), 0.0, 0.0]
            if target == "action" or idempotent
            else [float(-(1 - p) * (1 - q) / 2), float((1 + p) * (1 - q) / 2), 0.0]
        )
        interaction = 0.0 if target == "action" or idempotent else float((1 - p) * (1 - q))
    else:
        shares, interaction = None, None
    return {
        "coalition_bad_rates": rates,
        "unknown_probabilities": unknown,
        "shapley_eligible": eligible,
        "shapley_values": shares,
        "selection_retry_interaction": interaction,
        "endpoint_eligible": rates[0] is not None and rates[7] is not None,
        "endpoint_difference": rates[7] - rates[0]
        if rates[0] is not None and rates[7] is not None
        else None,
        "reason": None if eligible else "positive invalid or unknown population mass",
    }, valid


def audit(root, expected_source=None):
    import jsonschema

    root = Path(root).resolve()
    checks = 0

    def check(value, label):
        nonlocal checks
        checks += 1
        if not value:
            raise AssertionError(label)

    def compare(actual, expected, label):
        if type(expected) is dict:
            check(type(actual) is dict and set(actual) == set(expected), label + " keys")
            for key in expected:
                compare(actual[key], expected[key], label + "/" + str(key))
        elif type(expected) in (list, tuple):
            check(type(actual) is list and len(actual) == len(expected), label + " length")
            for i, value in enumerate(expected):
                compare(actual[i], value, label + "/" + str(i))
        elif type(expected) in (float, int) and type(expected) is not bool:
            check(
                type(actual) in (float, int)
                and math.isfinite(actual)
                and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-11),
                label,
            )
        else:
            check(actual == expected and type(actual) is type(expected), label)

    def load(name):
        return decode((root / name).read_text(encoding="utf-8"))

    def gz(name):
        with gzip.open(root / name, "rt", encoding="utf-8") as stream:
            return decode(stream.read())

    def measurement(actual, operations, spec):
        _, _, idempotent, provenance, lag, _ = spec
        selected = operations[0] == "refund"
        refunded = int(selected) * (1 if idempotent or "retry" not in operations else 2)
        state = None if lag else refunded == 1
        linked = None if state is None or (state and not provenance) else state
        expected = {
            "target_values": {
                "action": selected,
                "consequence": state,
                "action_linked_consequence": linked,
            },
            "verification": "unknown" if lag else "satisfied" if refunded == 1 else "violated",
            "origin": "confirmed" if selected and provenance and not lag else "unknown",
            "watermark_ms": 0 if lag else 100,
            "horizon_ms": 100,
            "available": True,
            "complete": True,
            "readback_records": 0 if lag else refunded,
            "matching_count": None if lag else refunded,
            "eligible_count": None if lag else refunded,
            "peak_matching_count": None if lag else refunded,
            "linked_count": refunded if provenance and not lag else 0,
        }
        check(set(actual) == set(expected) | {"trace_sha256"}, "measurement field inventory")
        for field, value in expected.items():
            compare(actual[field], value, "independent measurement/" + field)
        digest = actual["trace_sha256"]
        check(
            type(digest) is str
            and len(digest) == 64
            and all(char in "0123456789abcdef" for char in digest),
            "canonical public trace digest",
        )
        return expected["target_values"]

    manifest = load("manifest.json")
    check(
        manifest["status"] == "completed" and manifest["completed"] is True, "completion manifest"
    )
    names = set()
    for item in manifest["artifacts"]:
        check(set(item) == {"path", "sha256", "bytes"}, "manifest fields")
        name = item["path"]
        canonical = PurePosixPath(name)
        check(
            type(name) is str
            and canonical.as_posix() == name
            and not canonical.is_absolute()
            and all(
                part not in ("", ".", "..") and ":" not in part and "\\" not in part
                for part in name.split("/")
            ),
            "safe canonical path",
        )
        check(name not in names, "unique inventory path")
        names.add(name)
        path = (root / name).resolve()
        check(
            path.is_relative_to(root) and path != root / "manifest.json", "contained artifact path"
        )
        data = path.read_bytes()
        compare(item["bytes"], len(data), "artifact byte size")
        compare(item["sha256"], sha256(data).hexdigest(), "artifact hash")
    check(
        names
        == {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path != root / "manifest.json"
        },
        "complete file inventory",
    )
    protocol = load("protocol.json")
    summary = load("summary.json")
    check(protocol["schema_version"] == "refund-interaction-sampling-v1", "schema version")
    check(
        type(protocol["package_version"]) is str and bool(protocol["package_version"]),
        "nonempty package version",
    )
    compare(manifest["package_version"], protocol["package_version"], "manifest package version")
    compare(
        protocol["collection_intervals"],
        {"pair": "normal", "endpoint": "normal"},
        "declared collection intervals",
    )
    compare(
        protocol["comparison_intervals"],
        {"pair": "hoeffding", "endpoint": "clopper_pearson_difference"},
        "declared comparison intervals",
    )
    execution = protocol["execution"]
    workers = execution["workers"]
    check(type(workers) is int and 1 <= workers <= 8, "declared worker count")
    compare(
        execution,
        {
            "workers": workers,
            "max_in_flight": 2 * workers if workers > 1 else 1,
            "result_order": "declared_trial_schedule",
            "resampling_on_failure": False,
        },
        "bounded ordered execution declaration",
    )
    check(
        type(protocol["source_revision"]) is str and bool(protocol["source_revision"].strip()),
        "source identifier",
    )
    if expected_source is not None:
        compare(protocol["source_revision"], expected_source, "expected source")
    plan = protocol["plan"]
    for field, minimum in (
        ("repeats", 1),
        ("pairs", 2),
        ("samples_per_eval", 1),
        ("endpoint_samples", 2),
        ("seed", 20000000),
        ("max_calls", 3),
    ):
        check(type(plan[field]) is int and plan[field] >= minimum, "plan integer " + field)
    check(
        type(plan["confidence"]) in (int, float)
        and math.isfinite(plan["confidence"])
        and 0 < plan["confidence"] < 1,
        "plan confidence",
    )
    for field, allowed in (("mechanisms", SPECS), ("games", ("strict", "on_reach"))):
        values = plan[field]
        check(
            type(values) is list
            and bool(values)
            and all(type(item) is str and item in allowed for item in values)
            and len(set(values)) == len(values),
            "plan inventory " + field,
        )
    R, P, S, E, c = (
        plan[key]
        for key in ("repeats", "pairs", "samples_per_eval", "endpoint_samples", "confidence")
    )
    branches_per_trial = 2 * E + 8 * P * S
    N = len(plan["mechanisms"]) * len(plan["games"]) * R
    phase_end = (plan["seed"] + N * (1 + branches_per_trial)) * 6
    check(phase_end - 1 <= 2**31 - 1 and phase_end + N - 1 <= 2**31 - 1, "reserved key ranges")
    compare(protocol["planned_trials"], N, "planned trials")
    compare(protocol["planned_branches"], N * branches_per_trial, "planned branches")
    compare(protocol["targets"], list(TARGETS), "targets")
    compare(protocol["variants"], list(VARIANTS), "variants")
    expected_inventory = {"protocol.json", "summary.json", "trace-schema.json", "README.md"}
    for name in plan["mechanisms"]:
        for game in plan["games"]:
            stem = f"{name}__{game}"
            expected_inventory.update(
                {
                    f"trials/{stem}.jsonl.gz",
                    f"evidence/{stem}.json.gz",
                    f"evaluator_truth/{stem}.json.gz",
                }
            )
    check(names == expected_inventory, "exact predeclared artifact inventory")
    check(set(protocol["mechanisms"]) == set(plan["mechanisms"]), "mechanism inventory")
    check(set(protocol["references"]) == set(plan["mechanisms"]), "reference inventory")
    for name in plan["mechanisms"]:
        spec = SPECS[name]
        compare(
            protocol["mechanisms"][name],
            dict(
                zip(
                    (
                        "name",
                        "selection_probability",
                        "retry_probability",
                        "use_idempotency",
                        "include_provenance",
                        "read_lag_ms",
                        "max_calls",
                    ),
                    (name, *spec),
                )
            ),
            "fixed mechanism",
        )
        check(set(protocol["references"][name]) == set(plan["games"]), "reference game inventory")
        for game in plan["games"]:
            reference = protocol["references"][name][game]
            target_references = {}
            for target in TARGETS:
                expected, valid = _reference(spec, game, target)
                target_references[target] = expected
            compare(
                reference,
                {
                    "name": name,
                    "coalition_game": game,
                    "decision_count": 3,
                    "selection_probability": spec[0],
                    "retry_probability": spec[1],
                    "population_not_finite_seed_claim": True,
                    "coalition_valid_probabilities": valid,
                    "targets": target_references,
                },
                "independent population reference",
            )
    validator = jsonschema.Draft202012Validator(load("trace-schema.json"))
    groups = defaultdict(
        lambda: {
            "statuses": Counter(),
            "calls": Counter(),
            "inactive": 0,
            "numeric": defaultdict(list),
            "refusals": defaultdict(Counter),
            "interaction": defaultdict(list),
        }
    )
    trial_index = 0
    full_traces = 0
    for name in plan["mechanisms"]:
        spec = SPECS[name]
        p, q, idempotent, provenance, lag, _ = spec
        for game in plan["games"]:
            group = groups[(name, game)]
            stem = f"{name}__{game}"
            public, gold = (
                gz("evidence/" + stem + ".json.gz"),
                gz("evaluator_truth/" + stem + ".json.gz"),
            )
            expected_public_keys, expected_gold_keys = set(), set()
            with gzip.open(
                root / "trials" / (stem + ".jsonl.gz"), "rt", encoding="utf-8"
            ) as stream:
                for rep in range(R):
                    line = stream.readline()
                    check(bool(line), "all planned repetitions retained")
                    row = decode(line)
                    compare(row["schema_version"], protocol["schema_version"], "row schema version")
                    compare(row["error"], None, "no undeclared trial failure")
                    factual_seed = plan["seed"] + trial_index * (1 + branches_per_trial)
                    entry = {
                        "index": trial_index,
                        "mechanism": name,
                        "coalition_game": game,
                        "replicate": rep,
                        "factual_seed": factual_seed,
                        "continuation_seed": factual_seed + 1,
                        "permutation_seed": phase_end + trial_index,
                        "planned_branches": branches_per_trial,
                        "max_calls": 4 if name == "budget-p50-q50" else plan["max_calls"],
                    }
                    compare(row["trial_plan"], entry, "trial schedule")
                    compare(protocol["trial_schedule"][trial_index], entry, "protocol schedule")
                    rng = random.Random(entry["permutation_seed"])
                    orders = []
                    for _ in range(P):
                        order = [0, 1, 2]
                        rng.shuffle(order)
                        orders.append(order)
                    compare(row["permutations"], orders, "permutation RNG")
                    slots = []

                    def slot(role, pair, walk, step, held, sample):
                        i = len(slots)
                        slots.append(
                            {
                                "index": i,
                                "role": role,
                                "pair_index": pair,
                                "walk": walk,
                                "step": step,
                                "held_indices": sorted(held),
                                "sample_index": sample,
                                "continuation_seed": factual_seed + 1 + i,
                            }
                        )

                    for role, held in (("endpoint_empty", ()), ("endpoint_full", (0, 1, 2))):
                        for sample in range(E):
                            slot(role, None, None, None, held, sample)
                    for pair, order in enumerate(orders):
                        for walk, sequence in (
                            ("forward", order),
                            ("reverse", list(reversed(order))),
                        ):
                            for step in range(4):
                                for sample in range(S):
                                    slot("walk", pair, walk, step, sequence[:step], sample)
                    compare(row["slots"], slots, "complete exact slot schedule")
                    check(len(row["branches"]) == branches_per_trial, "branch inventory size")
                    check(row["factual"]["status"] == "completed", "planted factual captured")
                    compare(row["factual"]["calls"], 3, "three factual calls")
                    measurement(row["factual"]["measurement"], ["refund", "retry", "stop"], spec)
                    compare(
                        [
                            item["reply"]["decision"]["operation"]
                            for item in row["factual"]["decisions"]
                        ],
                        ["refund", "retry", "stop"],
                        "factual operations",
                    )
                    for phase, item in enumerate(row["factual"]["decisions"]):
                        compare(item["index"], phase, "factual receipt index")
                        compare(
                            item["stage"],
                            "select" if phase == 0 else "after_response",
                            "factual stage",
                        )
                        compare(item["model_seed"], factual_seed * 6 + phase, "factual phase key")
                        compare(item["policy_calls"], 1, "factual fresh cost")
                        compare(item["error_type"], None, "factual error type")
                        compare(item["error"], None, "factual error")
                    used, stopped = 3, False
                    values = {target: {} for target in TARGETS}
                    labels = {target: {} for target in TARGETS}
                    for item, branch in zip(slots, row["branches"]):
                        i, held = item["index"], set(item["held_indices"])
                        compare(branch["slot_index"], i, "unique ordered branch slot")
                        before = used
                        decisions = []
                        operations = []
                        if stopped:
                            expected_status, unreached, inactive = "unstarted", None, []
                        else:
                            expected_status = "completed"
                            for phase in range(3):
                                source = "held_factual" if phase in held else "resampled"
                                seed = item["continuation_seed"] * 6 + phase
                                failed = source == "resampled" and used >= entry["max_calls"]
                                if failed:
                                    operation, cost = None, 0
                                elif source == "held_factual":
                                    operation, cost = ("refund", "retry", "stop")[phase], 0
                                else:
                                    cost = 1
                                    used += 1
                                    operation = (
                                        ("refund" if random.Random(seed).random() < p else "stop")
                                        if phase == 0
                                        else (
                                            "retry" if random.Random(seed).random() < q else "stop"
                                        )
                                        if phase == 1
                                        else "stop"
                                    )
                                decision = {
                                    "index": phase,
                                    "source": source,
                                    "stage": "select" if phase == 0 else "after_response",
                                    "continuation_model_seed": seed,
                                    "factual_model_seed": factual_seed * 6 + phase,
                                    "factual_event_id": "refund_decision"
                                    if phase == 0
                                    else f"response_decision_{phase}",
                                    "policy_calls": cost,
                                    "operation": operation,
                                    "attempts_remaining": 2 - phase,
                                    "response_statuses": []
                                    if phase == 0
                                    else ["timeout"]
                                    if phase == 1
                                    else ["timeout", "success"],
                                    "error_type": "CallBudgetExceeded" if failed else None,
                                    "error": "The policy-call budget is exhausted"
                                    if failed
                                    else None,
                                }
                                decisions.append(decision)
                                if failed:
                                    expected_status, stopped = "failed", True
                                    break
                                operations.append(operation)
                                if operation == "stop":
                                    break
                            unreached = sorted(index for index in held if index >= len(decisions))
                            if expected_status == "completed" and game == "strict" and unreached:
                                expected_status = "invalid"
                            inactive = (
                                unreached
                                if expected_status == "completed" and game == "on_reach"
                                else []
                            )
                        compare(branch["status"], expected_status, "independent branch status")
                        expected_error_type = (
                            "CallBudgetExceeded"
                            if expected_status == "failed"
                            else "DecisionCoalitionUnreachable"
                            if expected_status == "invalid"
                            else None
                        )
                        expected_error = (
                            "The policy-call budget is exhausted"
                            if expected_status == "failed"
                            else f"Held decision positions were not reached: {tuple(unreached)}"
                            if expected_status == "invalid"
                            else None
                        )
                        compare(branch["error_type"], expected_error_type, "branch error type")
                        compare(branch["error"], expected_error, "branch error")
                        compare(
                            branch["budget_exhausted"],
                            expected_status == "failed",
                            "branch budget exhaustion",
                        )
                        compare(branch["policy_calls"], used - before, "independent branch calls")
                        compare(
                            branch["unreached_held_indices"], unreached, "unreached held positions"
                        )
                        compare(
                            branch["inactive_held_indices"], inactive, "inactive held positions"
                        )
                        check(
                            len(branch["decisions"]) == len(decisions), "decision receipt inventory"
                        )
                        for actual, expected in zip(branch["decisions"], decisions):
                            for key, value in expected.items():
                                compare(actual[key], value, "independent reached receipt " + key)
                        group["statuses"][expected_status] += 1
                        group["inactive"] += bool(inactive)
                        if expected_status == "completed":
                            target_values = measurement(branch["measurement"], operations, spec)
                            for target, value in target_values.items():
                                values[target][i] = None if value is None else int(not value)
                                labels[target][i] = "unknown" if value is None else "known"
                        else:
                            check(branch["measurement"] is None, "no fabricated measurement")
                            for target in TARGETS:
                                values[target][i], labels[target][i] = None, expected_status
                        if rep == 0 and expected_status != "unstarted":
                            expected_public_keys.add(f"branch_{i}")
                        if rep == 0 and expected_status == "completed":
                            expected_gold_keys.add(f"branch_{i}")
                    compare(
                        row["calls"],
                        {
                            "factual": 3,
                            "continuations": used - 3,
                            "total": used,
                            "additional_comparison": 0,
                        },
                        "total/counter accounting",
                    )
                    group["calls"].update(row["calls"])
                    statuses = Counter(branch["status"] for branch in row["branches"])
                    for variant in VARIANTS:
                        data = row["variants"][variant]
                        local_summary = data["summary"]
                        summary_fields = {
                            "factual_decision_count": 3,
                            "pairs": P,
                            "permutations": 2 * P,
                            "samples_per_eval": S,
                            "endpoint_samples_per_coalition": E,
                            "planned_branches": branches_per_trial,
                            "attempted_branches": branches_per_trial - statuses["unstarted"],
                            "completed_branches": statuses["completed"],
                            "invalid_branches": statuses["invalid"],
                            "failed_branches": statuses["failed"],
                            "not_started_branches": statuses["unstarted"],
                            "policy_calls": used - 3,
                            "shared_budget_calls_before": 3,
                            "shared_budget_calls_after": used,
                            "max_calls": entry["max_calls"],
                            "budget_exhausted": stopped,
                            "estimates": {
                                target: {
                                    status: sum(
                                        value["target"] == target and value["status"] == status
                                        for value in data["estimates"]
                                    )
                                    for status in ("estimated", "refused")
                                }
                                for target in TARGETS
                            },
                            "endpoint_checks": data["endpoint_checks"],
                        }
                        for field, expected_value in summary_fields.items():
                            compare(local_summary[field], expected_value, "local summary/" + field)
                        method_fields = {
                            "name": "car_style_binary_decision_shapley"
                            if game == "strict"
                            else "binary_on_reach_decision_shapley",
                            "coalition_game": game,
                            "pairs": P,
                            "samples_per_eval": S,
                            "endpoint_samples": E,
                            "confidence": c,
                            "permutation_seed": entry["permutation_seed"],
                            "interval_method": "normal pair-mean interval; sample variance ddof=1 divided by pairs"
                            if variant == "normal"
                            else "two-sided Hoeffding pair-mean bound",
                            "endpoint_interval_method": "normal"
                            if variant == "normal"
                            else "clopper_pearson_difference",
                            "pair_value_bounds": [-1.0, 1.0],
                            "interval_clipping": variant != "normal",
                            "independent_unit": "one averaged forward/reverse contribution vector",
                            "multiplicity_adjustment": "none",
                            "missingness_policy": "any missing path draw refuses the whole target vector; no redraws",
                            "endpoint_missingness": "endpoint diagnostics refused separately from path coefficients",
                        }
                        for field, expected_value in method_fields.items():
                            compare(
                                local_summary["method"][field], expected_value, "method/" + field
                            )
                    for target in TARGETS:
                        path = [item for item in slots if item["role"] == "walk"]
                        coverage = {
                            "planned": len(path),
                            **{
                                label: sum(labels[target][item["index"]] == label for item in path)
                                for label in ("known", "unknown", "invalid", "failed", "unstarted")
                            },
                        }
                        pairs, pair_labels = [], []
                        for pair, order in enumerate(orders):
                            selected_slots = [item for item in path if item["pair_index"] == pair]
                            label = next(
                                (
                                    label
                                    for label in ("unstarted", "failed", "invalid", "unknown")
                                    if any(
                                        labels[target][item["index"]] == label
                                        for item in selected_slots
                                    )
                                ),
                                "known",
                            )
                            pair_labels.append(label)
                            if label != "known":
                                pairs.append(None)
                                continue
                            vector = [0.0, 0.0, 0.0]
                            for walk, sequence in (
                                ("forward", order),
                                ("reverse", list(reversed(order))),
                            ):
                                means = [
                                    sum(
                                        values[target][item["index"]]
                                        for item in selected_slots
                                        if item["walk"] == walk and item["step"] == step
                                    )
                                    / S
                                    for step in range(4)
                                ]
                                for step, position in enumerate(sequence):
                                    vector[position] += (means[step + 1] - means[step]) / 2
                            pairs.append(vector)
                        for variant in VARIANTS:
                            data = row["variants"][variant]
                            check(
                                data is not None and len(data["estimates"]) == 9,
                                "variant coefficient inventory",
                            )
                            check(
                                {(v["target"], v["decision_index"]) for v in data["estimates"]}
                                == {(t, j) for t in TARGETS for j in range(3)},
                                "complete unique coefficients",
                            )
                            for position in range(3):
                                estimate = next(
                                    v
                                    for v in data["estimates"]
                                    if v["target"] == target and v["decision_index"] == position
                                )
                                compare(
                                    estimate["event_id"],
                                    "refund_decision"
                                    if position == 0
                                    else f"response_decision_{position}",
                                    "coefficient event identity",
                                )
                                vector = [
                                    pair[position] if pair is not None else None for pair in pairs
                                ]
                                compare(
                                    estimate["pair_values"], vector, "raw pair coefficient values"
                                )
                                compare(estimate["coverage"], coverage, "path coverage")
                                for label in ("known", "unknown", "invalid", "failed", "unstarted"):
                                    compare(
                                        estimate[label + "_pairs"],
                                        pair_labels.count(label),
                                        "pair-status denominator",
                                    )
                                key = (variant, target, position)
                                available = all(pair is not None for pair in pairs)
                                compare(
                                    estimate["status"],
                                    "estimated" if available else "refused",
                                    "vector refusal",
                                )
                                if available:
                                    point, bound = (
                                        sum(vector) / P,
                                        _pair_interval(vector, c, variant),
                                    )
                                    compare(estimate["shapley_value"], point, "coefficient point")
                                    compare(
                                        estimate["confidence_interval"],
                                        bound,
                                        "independent pair interval",
                                    )
                                    compare(
                                        estimate["reason"], None, "available coefficient reason"
                                    )
                                    compare(
                                        estimate["interval_degenerate"],
                                        bound[0] == bound[1],
                                        "coefficient degeneracy flag",
                                    )
                                    group["numeric"][key].append((point, bound))
                                else:
                                    check(
                                        estimate["shapley_value"] is None
                                        and estimate["confidence_interval"] is None,
                                        "refused coefficient null",
                                    )
                                    compare(
                                        estimate["interval_degenerate"],
                                        None,
                                        "refused degeneracy flag",
                                    )
                                    reason = next(
                                        label
                                        for label in ("unstarted", "failed", "invalid", "unknown")
                                        if coverage[label]
                                    )
                                    group["refusals"][key][reason] += 1
                            check(
                                len(data["endpoint_checks"]) == 3
                                and {v["target"] for v in data["endpoint_checks"]} == set(TARGETS),
                                "complete unique endpoints",
                            )
                            endpoint = next(
                                v for v in data["endpoint_checks"] if v["target"] == target
                            )
                            roles = {
                                role: [item for item in slots if item["role"] == role]
                                for role in ("endpoint_empty", "endpoint_full")
                            }
                            covers = {}
                            for role, items in roles.items():
                                covers[role] = {
                                    "planned": E,
                                    **{
                                        label: sum(
                                            labels[target][item["index"]] == label for item in items
                                        )
                                        for label in (
                                            "known",
                                            "unknown",
                                            "invalid",
                                            "failed",
                                            "unstarted",
                                        )
                                    },
                                }
                                compare(
                                    endpoint[
                                        "empty_coverage"
                                        if role == "endpoint_empty"
                                        else "full_coverage"
                                    ],
                                    covers[role],
                                    "endpoint coverage",
                                )
                            available = all(value["known"] == E for value in covers.values())
                            compare(
                                endpoint["status"],
                                "estimated" if available else "refused",
                                "endpoint availability",
                            )
                            key = (variant, target, "endpoint")
                            coefficient_sum = (
                                sum(
                                    sum(pair[position] for pair in pairs) / P
                                    for position in range(3)
                                )
                                if all(pair is not None for pair in pairs)
                                else None
                            )
                            compare(endpoint["coefficient_sum"], coefficient_sum, "coefficient sum")
                            if available:
                                empty, full = [
                                    [values[target][item["index"]] for item in roles[role]]
                                    for role in ("endpoint_empty", "endpoint_full")
                                ]
                                difference = sum(full) / E - sum(empty) / E
                                bound = _endpoint_interval(empty, full, c, variant)
                                compare(endpoint["empty_bad_rate"], sum(empty) / E, "empty rate")
                                compare(endpoint["full_bad_rate"], sum(full) / E, "full rate")
                                compare(
                                    endpoint["endpoint_difference"], difference, "endpoint effect"
                                )
                                compare(
                                    endpoint["confidence_interval"],
                                    bound,
                                    "independent endpoint interval",
                                )
                                compare(endpoint["reason"], None, "available endpoint reason")
                                compare(
                                    endpoint["discrepancy"],
                                    coefficient_sum - difference
                                    if coefficient_sum is not None
                                    else None,
                                    "descriptive endpoint discrepancy",
                                )
                                group["numeric"][key].append((difference, bound))
                            else:
                                check(
                                    endpoint["endpoint_difference"] is None
                                    and endpoint["confidence_interval"] is None,
                                    "refused endpoint null",
                                )
                                compare(endpoint["empty_bad_rate"], None, "refused empty rate")
                                compare(endpoint["full_bad_rate"], None, "refused full rate")
                                compare(endpoint["discrepancy"], None, "refused discrepancy")
                                reason = next(
                                    label
                                    for label in ("unstarted", "failed", "invalid", "unknown")
                                    if any(value[label] for value in covers.values())
                                )
                                group["refusals"][key][reason] += 1
                        cells = {mask: [] for mask in (0, 1, 2, 3)}
                        missing = False
                        for item in slots:
                            mask = sum(1 << i for i in item["held_indices"])
                            if mask not in cells:
                                continue
                            value = values[target][item["index"]]
                            if value is None:
                                missing = True
                            else:
                                cells[mask].append(value)
                        if not missing and all(cells.values()):
                            means = {mask: sum(v) / len(v) for mask, v in cells.items()}
                            group["interaction"][target].append(
                                (means[3] - means[1] - means[2] + means[0], None)
                            )
                    if rep == 0:
                        compare(public["trial_plan"], entry, "full evidence trial identity")
                        compare(gold["trial_plan"], entry, "gold trial identity")
                        check(
                            set(public["branches"]) == expected_public_keys,
                            "full attempted branch inventory",
                        )
                        check(
                            set(gold["episodes"]) == expected_gold_keys | {"factual"},
                            "full completed gold inventory",
                        )
                        compare(
                            public["factual"]["decisions"],
                            row["factual"]["decisions"],
                            "full factual receipt identity",
                        )
                        for branch_key in sorted(expected_public_keys):
                            index = int(branch_key.split("_")[1])
                            compact = row["branches"][index]
                            record = public["branches"][branch_key]
                            compare(record["slot"], slots[index], "full exact branch slot")
                            decisions = compact["decisions"]
                            expected_branch_summary = {
                                "status": compact["status"],
                                "coalition_game": game,
                                "inactive_held_indices": compact["inactive_held_indices"],
                                "held_indices": slots[index]["held_indices"],
                                "continuation_seed": slots[index]["continuation_seed"],
                                "factual_seed": factual_seed,
                                "factual_decision_count": 3,
                                "reached_decisions": len(decisions),
                                "held_decisions": sum(
                                    item["source"] == "held_factual"
                                    and item["operation"] is not None
                                    for item in decisions
                                ),
                                "resampled_decisions": sum(
                                    item["source"] == "resampled" and item["operation"] is not None
                                    for item in decisions
                                ),
                                "held_requests": sum(
                                    item["source"] == "held_factual" for item in decisions
                                ),
                                "resampled_requests": sum(
                                    item["source"] == "resampled" for item in decisions
                                ),
                                "failed_decisions": sum(
                                    item["error_type"] is not None for item in decisions
                                ),
                                "unreached_factual_indices": list(range(len(decisions), 3)),
                                "unreached_held_indices": compact["unreached_held_indices"],
                                "policy_calls": compact["policy_calls"],
                                "budget_exhausted": compact["budget_exhausted"],
                                "error_type": compact["error_type"],
                                "error": compact["error"],
                            }
                            compare(
                                record["summary"], expected_branch_summary, "full branch summary"
                            )
                            check(
                                len(record["decisions"]) == len(decisions), "full receipt inventory"
                            )
                            for receipt, expected_receipt in zip(record["decisions"], decisions):
                                projected = {
                                    field: receipt[field]
                                    for field in (
                                        "index",
                                        "source",
                                        "stage",
                                        "continuation_model_seed",
                                        "factual_model_seed",
                                        "factual_event_id",
                                        "policy_calls",
                                        "error_type",
                                        "error",
                                    )
                                }
                                reply = receipt["reply"]
                                projected.update(
                                    operation=reply["decision"]["operation"] if reply else None,
                                    attempts_remaining=receipt["request"]["attempts_remaining"],
                                    response_statuses=[
                                        item["status"] for item in receipt["request"]["responses"]
                                    ],
                                )
                                compare(projected, expected_receipt, "full reached receipt")
                        for key in ("factual", *sorted(expected_gold_keys)):
                            record = (
                                public["factual"] if key == "factual" else public["branches"][key]
                            )
                            trace = record["trace"]
                            validator.validate(trace)
                            full_traces += 1
                            measured = (
                                row["factual"]["measurement"]
                                if key == "factual"
                                else row["branches"][int(key.split("_")[1])]["measurement"]
                            )
                            compare(
                                sha256(
                                    json.dumps(
                                        trace,
                                        sort_keys=True,
                                        allow_nan=False,
                                        separators=(",", ":"),
                                    ).encode()
                                ).hexdigest(),
                                measured["trace_sha256"],
                                "full trace hash",
                            )
                            compare(
                                trace["verifications"][-1]["status"],
                                measured["verification"],
                                "full verifier status",
                            )
                            compare(
                                trace["verifications"][-1]["origin"],
                                measured["origin"],
                                "full origin",
                            )
                            compare(
                                trace["observations"][-1]["as_of_ms"],
                                measured["watermark_ms"],
                                "full watermark",
                            )
                            compare(
                                len(trace["observations"][-1]["records"]),
                                measured["readback_records"],
                                "full record count",
                            )
                            compare(
                                len(trace["verifications"][-1]["attributable_effect_ids"]),
                                measured["linked_count"],
                                "full linked effect count",
                            )
                            action = trace["action"]
                            compare(
                                action["action_id"],
                                f"refund:{factual_seed}",
                                "logical operation identity",
                            )
                            compare(action["actor"], "RefundAgent", "logical actor")
                            expected_payload = {
                                "payment_id": "pay_42",
                                "amount_minor": 500000,
                                "currency": "INR",
                            }
                            compare(
                                action["arguments"], expected_payload, "frozen refund arguments"
                            )
                            compare(
                                action["contract"]["expected"],
                                expected_payload,
                                "frozen contract parameters",
                            )
                            compare(action["contract"]["exact_count"], 1, "exact-one contract")
                            compare(action["contract"]["deadline_ms"], 100, "contract deadline")
                            compare(action["contract"]["stability_ms"], 0, "stability horizon")
                            compare(
                                action["idempotency_key"],
                                f"consequa-refund-{factual_seed}" if idempotent else None,
                                "idempotency setting",
                            )
                            captured = [
                                event
                                for event in trace["events"]
                                if event["type"] == "agent_decision"
                            ]
                            observed_ops = [
                                event["data"]["policy_reply"]["decision"]["operation"]
                                for event in captured
                            ]
                            expected_ops = (
                                ["refund", "retry", "stop"]
                                if key == "factual"
                                else [
                                    decision["operation"]
                                    for decision in row["branches"][int(key.split("_")[1])][
                                        "decisions"
                                    ]
                                ]
                            )
                            compare(observed_ops, expected_ops, "full captured decision operations")
                            check(
                                len(captured) == len(record["decisions"]),
                                "full event/receipt inventory",
                            )
                            for event, receipt in zip(captured, record["decisions"]):
                                compare(
                                    event["data"]["policy_request"],
                                    receipt["request"],
                                    "saved receipt request matches captured boundary",
                                )
                                compare(
                                    event["data"]["policy_reply"],
                                    receipt["reply"],
                                    "saved receipt reply matches captured decision",
                                )
                            for phase, event in enumerate(captured):
                                request = event["data"]["policy_request"]
                                compare(
                                    request["responses"],
                                    trace["responses"][:phase],
                                    "full public response prefix",
                                )
                                compare(
                                    request["attempts_remaining"], 2 - phase, "full attempt budget"
                                )
                                check(
                                    set(request)
                                    == {
                                        "stage",
                                        "task",
                                        "context",
                                        "responses",
                                        "attempts_remaining",
                                    },
                                    "public input boundary",
                                )
                            obs = trace["observations"][-1]
                            compare(obs["available"], True, "readback source available")
                            compare(obs["complete"], True, "exhaustive scoped snapshot")
                            compare(obs["scope"]["payment_id"], "pay_42", "readback payment scope")
                            truth = gold["episodes"][key]
                            compare(truth["seed"], factual_seed, "gold isolated world identity")
                            config = truth["config"]
                            compare(config["fault"], "timeout_after_commit", "frozen fault")
                            compare(config["include_provenance"], provenance, "frozen provenance")
                            compare(config["read_lag_ms"], lag, "frozen readback lag")
                            compare(config["use_idempotency"], idempotent, "frozen idempotency")
                            refunds = [
                                item for item in truth["records"] if item["kind"] == "refund"
                            ]
                            selected = expected_ops[0] == "refund"
                            refund_count = int(selected) * (
                                1 if idempotent or "retry" not in expected_ops else 2
                            )
                            compare(
                                len(refunds), refund_count, "independent committed-effect count"
                            )
                            visible = []
                            for item in refunds:
                                compare(item["amount_minor"], 500000, "committed minor units")
                                compare(item["payment_id"], "pay_42", "committed payment")
                                compare(item["currency"], "INR", "committed currency")
                                compare(item["actor"], "RefundAgent", "committed actor")
                                compare(
                                    item["action_id"],
                                    action["action_id"],
                                    "committed operation linkage",
                                )
                                if item["committed_at_ms"] <= obs["as_of_ms"]:
                                    visible.append(
                                        {
                                            field: value
                                            for field, value in item.items()
                                            if field != "kind"
                                            and (
                                                provenance
                                                or field not in {"actor", "action_id", "attempt_id"}
                                            )
                                        }
                                    )
                            compare(
                                obs["records"],
                                visible,
                                "readback projects recorded durable effects",
                            )
                            verified = trace["verifications"][-1]
                            for evidence in verified["evidence"]:
                                compare(
                                    evidence["observation_id"],
                                    obs["observation_id"],
                                    "evidence observation reference",
                                )
                                compare(evidence["source"], obs["source"], "evidence source")
                                compare(evidence["as_of_ms"], obs["as_of_ms"], "evidence watermark")
                                compare(
                                    evidence["details"]["records"],
                                    obs["records"],
                                    "evidence snapshot records",
                                )
                            compare(
                                record["explanation"]["consequence"],
                                verified,
                                "explanation supported consequence",
                            )
                            compare(
                                record["explanation"]["agent_assessment"],
                                trace["assessment"],
                                "explanation reported assessment",
                            )
                            compare(
                                record["explanation"]["assessment_alignment"],
                                "unassessable",
                                "unknown fixture assessment alignment",
                            )
                            events = {event["id"]: event for event in trace["events"]}
                            check(
                                len(events) == len(trace["events"]), "unique full event identities"
                            )
                            visited, visiting = set(), set()

                            def visit(event_id):
                                check(
                                    event_id in events and event_id not in visiting,
                                    "resolved acyclic full trace dependency",
                                )
                                if event_id in visited:
                                    return
                                visiting.add(event_id)
                                for parent in events[event_id]["parent_ids"]:
                                    visit(parent)
                                visiting.remove(event_id)
                                visited.add(event_id)

                            for event in events.values():
                                compare(
                                    event["trace_id"],
                                    trace["trace_id"],
                                    "consistent full trace identity",
                                )
                                visit(event["id"])
                            check(
                                "ground_truth" not in trace and "fault" not in trace,
                                "separate gold boundary",
                            )
                    trial_index += 1
                check(stream.readline() == "", "no extra trials")
    compare(trial_index, N, "retained trial count")
    check(len(protocol["trial_schedule"]) == N, "complete schedule inventory")
    expected = {
        "schema_version": "refund-interaction-sampling-v1",
        "planned_trials": N,
        "retained_trials": N,
        "planned_branches": N * branches_per_trial,
        "additional_comparison_policy_calls": 0,
        "branch_rows": [],
        "coefficient_rows": [],
        "endpoint_rows": [],
        "interaction_rows": [],
    }
    for name in plan["mechanisms"]:
        for game in plan["games"]:
            group = groups[(name, game)]
            expected["branch_rows"].append(
                {
                    "mechanism": name,
                    "coalition_game": game,
                    "planned_trials": R,
                    "planned_branches": R * branches_per_trial,
                    "status_counts": {
                        label: group["statuses"][label]
                        for label in ("completed", "invalid", "failed", "unstarted")
                    },
                    "inactive_held_branches": group["inactive"],
                    "calls": dict(group["calls"]),
                }
            )
            for variant in VARIANTS:
                for target in TARGETS:
                    reference, _ = _reference(SPECS[name], game, target)
                    for position in (0, 1, 2, "endpoint"):
                        key = (variant, target, position)
                        truth = (
                            reference["endpoint_difference"]
                            if position == "endpoint"
                            else reference["shapley_values"][position]
                            if reference["shapley_eligible"]
                            else None
                        )
                        result = {
                            "mechanism": name,
                            "coalition_game": game,
                            "variant": variant,
                            "target": target,
                            "decision_index": position,
                            **_metrics(group["numeric"][key], truth, R, c),
                            "refusal_counts": dict(group["refusals"][key]),
                        }
                        expected[
                            "endpoint_rows" if position == "endpoint" else "coefficient_rows"
                        ].append(result)
            for target in TARGETS:
                reference, _ = _reference(SPECS[name], game, target)
                expected["interaction_rows"].append(
                    {
                        "mechanism": name,
                        "coalition_game": game,
                        "target": target,
                        **_metrics(
                            group["interaction"][target],
                            reference["selection_retry_interaction"],
                            R,
                            c,
                        ),
                        "uncertainty": "point-only diagnostic pooled from existing draw occurrences; no interval",
                    }
                )
    expected["actual_policy_calls"] = sum(row["calls"]["total"] for row in expected["branch_rows"])
    compare(summary, expected, "all independent aggregates")
    return {
        "status": "passed",
        "audited_utc": datetime.now(timezone.utc).isoformat(),
        "assertions": checks,
        "trials": N,
        "branches": N * branches_per_trial,
        "full_traces": full_traces,
        "actual_policy_calls": expected["actual_policy_calls"],
        "generation_calls": 0,
        "source_revision": protocol["source_revision"],
        "manifest_sha256": sha256((root / "manifest.json").read_bytes()).hexdigest(),
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--expected-source")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = audit(args.directory, args.expected_source)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        path = Path(args.output)
        if path.exists() or path.resolve().is_relative_to(Path(args.directory).resolve()):
            raise ValueError("Audit output must be new and outside the sealed study")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
