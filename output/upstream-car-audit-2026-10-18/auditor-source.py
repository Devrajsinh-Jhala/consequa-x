"""Independent, read-only audit of recorded CAR/CX trial artefacts.

Uses only stdlib parsing/math. Never imports the collection implementation or
executes a policy, simulator trial, estimator, model or GitHub workflow.
Final auditing requires a terminal manifest or explicit incomplete receipt.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import subprocess


ENGINES = ("upstream_car", "consequa_x")
METHODS = ("contrastive", "shapley")
NATIVE_VARIANTS = {"contrastive": ("upstream_bootstrap",), "shapley": ("upstream_normal",)}
CX_VARIANTS = {"contrastive": ("cx_bootstrap", "cx_clopper_pearson"),
               "shapley": ("cx_normal", "cx_hoeffding")}
SPECS = {"refund-p50-q50": (Fraction(1, 2), Fraction(1, 2), False, False, False),
         "refund-p20-q80": (Fraction(1, 5), Fraction(4, 5), False, False, False),
         "refund-p80-q20": (Fraction(4, 5), Fraction(1, 5), False, False, False),
         "refund-p100-q100": (Fraction(1), Fraction(1), False, False, False),
         "idempotent-p50-q50": (Fraction(1, 2), Fraction(1, 2), True, False, False),
         "unknown-provenance-p50-q50": (Fraction(1, 2), Fraction(1, 2), False, True, False),
         "lagged-readback-p50-q50": (Fraction(1, 2), Fraction(1, 2), False, False, True),
         "budget-p50-q50": (Fraction(1, 2), Fraction(1, 2), False, False, False)}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def hash_bytes(content):
    return sha256(content).hexdigest()


def object_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def loads(content):
    return json.loads(content, object_pairs_hook=object_pairs)


def load(path):
    return loads(Path(path).read_bytes())


def assert_close(actual, expected, label="numeric", tolerance=1e-12):
    if actual is None or expected is None:
        assert actual is expected, (label, actual, expected)
    else:
        assert math.isfinite(actual) and math.isfinite(expected)
        assert abs(actual - expected) <= tolerance, (label, actual, expected)


def exact_reference(name):
    """Independent closed-form two-player law; terminal player is a dummy."""
    p, q, idem, missing, lag = SPECS[name]
    game, unknown = [], []
    for mask in range(8):
        s = Fraction(1) if mask & 1 else p
        r = Fraction(1) if mask & 2 else q
        good = s if idem else s * (1 - r)
        unknown_mass = Fraction(1) if lag else good if missing else Fraction(0)
        game.append(None if unknown_mass else 1 - good)
        unknown.append(unknown_mass)
    contrastive = [None if game[k] is None or game[7] is None else game[k] - game[7]
                   for k in (0, 1, 3)]
    shares = None if any(x is None for x in game) else [
        ((game[1] - game[0]) + (game[3] - game[2])) / 2,
        ((game[2] - game[0]) + (game[3] - game[1])) / 2, Fraction(0)]
    eligible = all(x is not None for x in contrastive)
    negative = [i for i, value in enumerate(contrastive) if value is not None and value < 0]
    def convert(values):
        return None if values is None else [None if x is None else float(x) for x in values]
    return {"coalition_bad_rates": convert(game), "unknown_probabilities": convert(unknown),
            "contrastive": convert(contrastive), "shapley": convert(shares),
            "population_locus_eligible": eligible,
            "latest_population_rescue": max(negative) if eligible and negative else None,
            "endpoint_difference": None if game[0] is None or game[7] is None else float(game[7] - game[0])}


def expected_slots(plan, trial):
    rows = []
    def append(role, held, **extra):
        index = len(rows)
        rows.append({"index": index, "role": role, "held_indices": sorted(held),
                     "continuation_seed": trial["continuation_seed"] + index, **extra})
    if trial["method"] == "contrastive":
        for position in range(3):
            for sample in range(plan["samples"]):
                append("contrastive", range(position), decision_index=position, sample_index=sample)
    else:
        for role, held in (("endpoint_empty", ()), ("endpoint_full", (0, 1, 2))):
            for sample in range(plan["endpoint_samples"]):
                append(role, held, sample_index=sample)
        rng = random.Random(trial["permutation_seed"])
        for pair in range(plan["pairs"]):
            order = list(range(3))
            rng.shuffle(order)
            for walk, path in (("forward", order), ("reverse", list(reversed(order)))):
                for step in range(4):
                    append("walk", path[:step], pair_index=pair, walk=walk, step=step, sample_index=0)
    return rows


def public_targets(action, observations, selected):
    """Independently interpret this study's exact-count refund snapshots only."""
    c = action["contract"]
    assert c["predicate"] == "refund_processed" and c["exact_count"] == 1
    observation = observations[-1]
    if (not observation["available"] or not observation["complete"]
            or observation["as_of_ms"] < c["deadline_ms"] + c["stability_ms"]):
        state = linked = None
    else:
        expected = c["expected"]
        assert observation["scope"]["payment_id"] == expected["payment_id"]
        relevant = [r for r in observation["records"] if
                    action["registered_at_ms"] <= r["committed_at_ms"]
                    <= c["deadline_ms"] + c["stability_ms"]]
        matching = [r for r in relevant if all(r[k] == expected[k] for k in
                    ("payment_id", "amount_minor", "currency"))]
        assert not any("reversed_at_ms" in r for r in matching), "No reversals are declared in this study"
        eligible = [r for r in matching if r["committed_at_ms"] <= c["deadline_ms"]]
        state = len(eligible) == 1 and len(matching) == 1
        if not state:
            linked = False
        elif eligible[0].get("action_id") == action["action_id"] and eligible[0].get("actor") == action["actor"]:
            linked = True
        elif all(r.get("actor") and r["actor"] != action["actor"]
                 and r.get("action_id") != action["action_id"] for r in relevant):
            linked = False
        else:
            linked = None
    return {"action": selected, "consequence": state, "action_linked_consequence": linked}


def normalized_decisions(decisions):
    normalized = []
    for original in decisions:
        item = dict(original)
        if item["source"] == "held_factual" and item["reply"] is not None:
            item["reply"] = dict(item["reply"])
            metadata = item["reply"]["metadata"]
            for wrapper in ("decision_prefix_replay", "decision_coalition_replay"):
                if wrapper in metadata:
                    metadata = metadata[wrapper]["factual_reply_metadata"]
                    break
            item["reply"]["metadata"] = metadata
        normalized.append(item)
    return normalized


def semantic_digest(value):
    def without_timing(item):
        if isinstance(item, dict):
            return {key: without_timing(nested) for key, nested in item.items()
                    if key not in {"elapsed_seconds", "glue_elapsed_seconds"}}
        if isinstance(item, list):
            return [without_timing(nested) for nested in item]
        return item
    return hash_bytes(canonical(without_timing(value)))


def raw_points(row, plan):
    receipts = row["receipts"]
    if row["trial"]["method"] == "contrastive":
        base = row["factual"]["evidence"]["bad"]
        return [sum(r["bad"] for r in receipts if r["slot"]["decision_index"] == position)
                / plan["samples"] - base for position in range(3)]
    pairs = []
    for pair in range(plan["pairs"]):
        walks = []
        for walk in ("forward", "reverse"):
            sequence = [r for r in receipts if r["slot"]["role"] == "walk"
                        and r["slot"]["pair_index"] == pair and r["slot"]["walk"] == walk]
            assert len(sequence) == 4 and [r["slot"]["step"] for r in sequence] == list(range(4))
            vector = [0., 0., 0.]
            for left, right in zip(sequence, sequence[1:]):
                added = set(right["slot"]["held_indices"]) - set(left["slot"]["held_indices"])
                assert len(added) == 1
                vector[added.pop()] = right["bad"] - left["bad"]
            walks.append(vector)
        pairs.append([(walks[0][i] + walks[1][i]) / 2 for i in range(3)])
    return [sum(pair[i] for pair in pairs) / len(pairs) for i in range(3)]


def audit_trial(row, plan, trial):
    assert row["trial"] == trial and row["engine"] in ENGINES
    slots = expected_slots(plan, trial)
    assert [r["slot"] for r in row["receipts"]] == slots
    factual = row["factual"]
    assert hash_bytes(canonical(factual["trace"])) == factual["evidence"]["trace_sha256"]
    trace = factual["trace"]
    assert factual["calls"] == 3
    event_decisions = [e for e in trace["events"] if e["type"] == "agent_decision"]
    assert [e["data"]["policy_reply"]["decision"]["operation"] for e in event_decisions] == ["refund", "retry", "stop"]
    assert [e["data"]["model_seed"] for e in event_decisions] == [trial["factual_seed"] * 6 + i for i in range(3)]
    expected_factual = public_targets(trace["action"], trace["observations"], True)
    assert factual["evidence"]["target_values"] == expected_factual
    target = trial["target"]
    expected_bad = None if expected_factual[target] is None else int(not expected_factual[target])
    assert factual["evidence"]["bad"] == expected_bad
    counts = Counter()
    coalesced_refusals = 0
    for receipt in row["receipts"]:
        status = receipt["status"]
        counts[status] += 1
        assert status in {"known", "unknown", "invalid", "failed", "unstarted"}
        decisions = receipt["decisions"]
        indices = [d["index"] for d in decisions]
        if indices != list(range(len(decisions))):
            # Pinned native coalition_distribution launches K coroutines with
            # gather. A cap refusal does not advance bridge.slot; fail_current
            # retains the whole batch's zero-spend refusals under one failed
            # canonical slot. This exception never admits a completed draw.
            assert row["engine"] == "upstream_car" and status == "failed"
            assert trial["mechanism"] == "budget-p50-q50" and trial["method"] == "contrastive"
            assert trial["max_calls"] == 4 and row["calls"]["total"] == 4
            assert receipt["error_type"] == "BudgetExceeded" and receipt["bad"] is None
            slot = receipt["slot"]
            assert slot["decision_index"] == 0 and slot["held_indices"] == []
            assert slot["sample_index"] == slot["index"] in (0, 1)
            if slot["index"] == 0:
                assert indices == [0, 1] + [0] * (plan["samples"] - 1)
                assert decisions[0]["reply"]["decision"]["operation"] == "refund"
                assert receipt["policy_calls"] == 1
                refusals = decisions[1:]
            else:
                assert indices == [0] * (plan["samples"] - 1)
                assert receipt["policy_calls"] == 0
                refusals = decisions
                assert row["receipts"][0]["status"] == "known"
                assert len(row["receipts"][0]["decisions"]) == 1
                assert row["receipts"][0]["decisions"][0]["reply"]["decision"]["operation"] == "stop"
            for decision in decisions:
                assert decision["source"] == "resampled"
                assert decision["request"] == event_decisions[decision["index"]]["data"]["policy_request"]
            for decision in refusals:
                assert decision["reply"] is None and decision["error_type"] == "CallBudgetExceeded"
            coalesced_refusals += len(refusals)
        actual = sum(d["source"] == "resampled" and d["reply"] is not None for d in decisions)
        assert actual == receipt["policy_calls"]
        for decision in decisions:
            assert decision["model_seed"] == receipt["slot"]["continuation_seed"] * 6 + decision["index"]
            assert (decision["source"] == "held_factual") == (decision["index"] in receipt["slot"]["held_indices"])
            if decision["source"] == "held_factual":
                reply = normalized_decisions([decision])[0]["reply"]
                assert reply == event_decisions[decision["index"]]["data"]["policy_reply"]
        if status in {"known", "unknown"}:
            selected = decisions[0]["reply"]["decision"]["operation"] == "refund"
            targets = public_targets(receipt["action"], receipt["observations"], selected)
            assert receipt["target_values"] == targets
            bad = None if targets[target] is None else int(not targets[target])
            assert receipt["bad"] == bad and (status == "unknown") == (bad is None)
            assert receipt["inactive_held_indices"] == sorted(set(receipt["slot"]["held_indices"]) - set(range(len(decisions))))
        else:
            assert receipt["bad"] is None
    gate = expected_bad is not None and counts["known"] == len(slots)
    assert row["gate"]["eligible"] is gate and row["gate"]["planned"] == len(slots)
    assert row["gate"]["counts"] == dict(counts)
    calls = row["calls"]
    continuation = sum(r["policy_calls"] for r in row["receipts"])
    assert calls == {"factual": 3, "continuation": continuation, "total": 3 + continuation, "cap": trial["max_calls"]}
    assert calls["total"] <= calls["cap"] and row["execution_cost"]["live_model_calls"] == 0
    cost = row["execution_cost"]
    assert math.isfinite(row["elapsed_seconds"]) and row["elapsed_seconds"] >= 0
    if row["engine"] == "upstream_car":
        assert row["deterministic_glue_reexecutions"] == cost["deterministic_glue_world_runs"]
        for name in ("deterministic_glue_world_runs", "completed_glue_world_runs", "glue_tool_dispatches",
                     "glue_reused_or_probe_decisions", "native_budget_charged_path_rollouts",
                     "supplemental_endpoint_rollouts"):
            assert type(cost[name]) is int and cost[name] >= 0
        assert cost["completed_glue_world_runs"] <= cost["deterministic_glue_world_runs"]
        assert math.isfinite(cost["glue_elapsed_seconds"]) and cost["glue_elapsed_seconds"] >= 0
    else:
        assert row["deterministic_glue_reexecutions"] is None
        assert cost["completed_replay_worlds"] == counts["known"] + counts["unknown"]
        assert cost["full_hold_preflight_worlds"] == 1
    names = NATIVE_VARIANTS[trial["method"]] if row["engine"] == "upstream_car" else CX_VARIANTS[trial["method"]]
    assert set(row["variants"]) == set(names)
    if row["engine"] == "upstream_car":
        assert row["unfiltered_diagnostic_eligible_for_inference"] is gate
    if not gate:
        assert all(not values for values in row["variants"].values()) and row["locus"] is None
    else:
        points = raw_points(row, plan)
        for values in row["variants"].values():
            assert [v["position"] for v in values] == list(range(3))
            for item, point in zip(values, points):
                assert_close(item["point"], point, "raw point")
                interval = item["interval"]
                assert len(interval) == 2 and all(math.isfinite(x) for x in interval)
                assert interval[0] <= interval[1]
        if trial["method"] == "contrastive":
            primary = next(iter(row["variants"].values()))
            rescues = [v["position"] for v in primary if v["point"] < 0 and v["interval"][1] < 0]
            assert row["locus"] == (max(rescues) if rescues else None)
    return {"gate": gate, "draw_status": dict(counts), "calls": calls["total"],
            "coalesced_zero_spend_budget_refusal_records": coalesced_refusals}


def pair_comparison(left, right):
    assert len(left["receipts"]) == len(right["receipts"])
    mismatches = []
    for a, b in zip(left["receipts"], right["receipts"]):
        fields = ("slot", "status", "policy_calls", "bad", "target_values", "action", "observations", "verifications")
        changed = [name for name in fields if a.get(name) != b.get(name)]
        if normalized_decisions(a["decisions"]) != normalized_decisions(b["decisions"]):
            changed.append("decisions")
        # This additional check is absent from the producer's comparison.
        if a.get("inactive_held_indices") != b.get("inactive_held_indices"):
            changed.append("inactive_held_indices")
        if changed:
            mismatches.append({"slot": a["slot"]["index"], "fields": sorted(changed)})
    point_differences = []
    native = next(iter(left["variants"].values()))
    for variant, values in right["variants"].items():
        if len(values) == len(native):
            for upstream, cx in zip(native, values):
                assert upstream["position"] == cx["position"]
                point_differences.append({"variant": variant, "position": cx["position"],
                    "absolute_difference": abs(upstream["point"] - cx["point"])})
    return {"same_factual_trace": left["factual"]["trace"] == right["factual"]["trace"],
            "same_actual_calls": left["calls"] == right["calls"],
            "draws_compared": len(left["receipts"]), "mismatches": mismatches,
            "point_differences": point_differences,
            "max_absolute_point_difference": max((x["absolute_difference"] for x in point_differences), default=None)}


def summary_row(items, reference, planned):
    estimates = [item for item in items if item is not None]
    errors = [] if reference is None else [x["point"] - reference for x in estimates]
    covered = None if reference is None else sum(x["interval"][0] <= reference <= x["interval"][1] for x in estimates)
    return {"planned": planned, "available": len(estimates), "reference": reference,
            "scored": len(errors), "covered": covered,
            "coverage_available": covered / len(errors) if errors else None,
            "coverage_planned": covered / planned if covered is not None else None,
            "bias": sum(errors) / len(errors) if errors else None,
            "rmse": math.sqrt(sum(x * x for x in errors) / len(errors)) if errors else None,
            "mean_width": sum(x["interval"][1] - x["interval"][0] for x in estimates) / len(estimates) if estimates else None,
            "zero_width": sum(x["interval"][0] == x["interval"][1] for x in estimates),
            "nonzero_flags": sum(x["interval"][0] > 0 or x["interval"][1] < 0 for x in estimates)}


def audit(study, snapshot, upstream, output, *, provisional=False):
    study, snapshot, upstream, output = map(lambda x: Path(x).resolve(), (study, snapshot, upstream, output))
    terminal = study / "manifest.json"
    incomplete = study / "incomplete-receipt.json"
    if not terminal.exists() and not incomplete.exists() and not provisional:
        return {"status": "awaiting_terminal_manifest", "trial_files_present": len(list((study / "trials").glob("*.json.gz"))),
                "final_audit_written": False}
    p = load(study / "protocol.json")
    plan = p["plan"]
    assert p["source_revision"] == "940ebfcc0059c992977dd8e9f112361ff5b31edd"
    assert plan == {"repeats": 64, "samples": 32, "pairs": 32, "endpoint_samples": 16,
                    "seed": 70000000, "max_calls": 1200, "confidence": .95, "workers": 4,
                    "mechanisms": list(SPECS)}
    assert p["engines"] == list(ENGINES) and len(p["trials"]) == 1024
    for name, claimed in p["source_files"].items():
        assert hash_bytes((snapshot / name).read_bytes()) == claimed, name
    provenance = load(study / "upstream-provenance.json")
    assert provenance["revision"] == p["upstream"]["revision"] == "db90fa28b97164c35e7c524e4597b8cbdb3035af"
    assert provenance["dependencies"] == p["execution_environment"]["dependencies"]
    revision = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    assert revision == provenance["revision"]
    status = subprocess.run(["git", "-C", str(upstream), "status", "--porcelain", "--untracked-files=all"],
                            check=True, capture_output=True, text=True).stdout
    assert not status.strip(), "Pinned upstream checkout changed or gained untracked source"
    for name, claimed in provenance["source_files"].items():
        assert hash_bytes((upstream / name).read_bytes()) == claimed, name
    references = {name: exact_reference(name) for name in SPECS}
    for name, exact in references.items():
        saved = p["references"][name]
        for key, value in exact.items():
            if isinstance(value, list):
                assert len(value) == len(saved[key])
                for x, y in zip(value, saved[key]):
                    assert_close(x, y, f"reference {name}/{key}")
            elif isinstance(value, float):
                assert_close(value, saved[key], f"reference {name}/{key}")
            else:
                assert value == saved[key], (name, key)
    complete = terminal.exists()
    if terminal.exists() or incomplete.exists():
        seal = load(terminal if complete else incomplete)
        assert seal.get("complete") is complete
        expected_files = set(seal["files"])
        for name, claimed in seal["files"].items():
            assert hash_bytes((study / name).read_bytes()) == claimed, name
        actual_files = {path.relative_to(study).as_posix() for path in study.rglob("*") if path.is_file()}
        assert actual_files == expected_files | {"manifest.json" if complete else "incomplete-receipt.json"}
    saved_disposition = load(study / "disposition.json") if (study / "disposition.json").exists() else None
    disposition_index = {g["trial"]["group_index"]: g for g in saved_disposition["groups"]} if saved_disposition else {}
    saved_pairs = load(study / "paired-validation.json") if (study / "paired-validation.json").exists() else None
    saved_pair_index = {g["trial"]["group_index"]: g for g in saved_pairs} if saved_pairs else {}
    semantic_bindings_checked = 0
    groups, compact = [], []
    draw_dispositions = defaultdict(Counter)
    totals = defaultdict(Counter)
    estimates = defaultdict(list)
    execution_costs = defaultdict(Counter)
    pair_details, parity_counts, mismatched_fields = [], Counter(), Counter()
    expected_paths = set()
    for index, trial in enumerate(p["trials"]):
        mechanism = plan["mechanisms"][index // (2 * plan["repeats"])]
        method = METHODS[index % 2]
        expected = {"group_index": index, "mechanism": mechanism, "replicate": (index // 2) % plan["repeats"],
                    "method": method, "factual_seed": 70000000 + index * 289,
                    "continuation_seed": 70000001 + index * 289, "permutation_seed": 210000000 + index,
                    "max_calls": 4 if mechanism.startswith("budget-") else 1200,
                    "target": "action_linked_consequence" if mechanism.startswith("unknown-provenance") else "consequence"}
        assert trial == expected
        rows = []
        for engine in ENGINES:
            path = study / "trials" / f"{index:05d}-{engine}.json.gz"
            expected_paths.add(path.relative_to(study).as_posix())
            if not path.exists():
                totals[(mechanism, method, engine)]["missing_engine_files"] += 1
                continue
            try:
                row = loads(gzip.decompress(path.read_bytes()))
            except (EOFError, OSError):
                if provisional:
                    totals[(mechanism, method, engine)]["in_progress_file"] += 1
                    continue
                raise
            assert row["engine"] == engine
            checked = audit_trial(row, plan, trial)
            rows.append(row)
            totals[(mechanism, method, engine)]["observed_engine_trials"] += 1
            totals[(mechanism, method, engine)]["eligible_engine_trials"] += checked["gate"]
            totals[(mechanism, method, engine)]["actual_policy_calls"] += checked["calls"]
            totals[(mechanism, method, engine)]["coalesced_zero_spend_budget_refusal_records"] += checked["coalesced_zero_spend_budget_refusal_records"]
            costs = execution_costs[(method, engine)]
            costs["engine_trials"] += 1
            for name in ("factual", "continuation", "total"):
                costs[f"fresh_policy_calls_{name}"] += row["calls"][name]
            costs["sum_per_trial_elapsed_seconds_under_four_worker_contention"] += row["elapsed_seconds"]
            for name, value in row["execution_cost"].items():
                if type(value) in (int, float):
                    costs[f"recorded_{name}"] += value
            draw_dispositions[(mechanism, method, engine)].update(checked["draw_status"])
            for variant, values in row["variants"].items():
                indexed = {v["position"]: v for v in values}
                for position in range(3):
                    estimates[(mechanism, method, variant, position)].append(indexed.get(position))
            compact.append({key: row[key] for key in ("trial", "engine", "variants", "gate", "calls", "locus")})
        if len(rows) == 2:
            comparison = pair_comparison(*rows)
            parity_counts["paired_groups"] += 1
            parity_counts["draws_compared"] += comparison["draws_compared"]
            parity_counts["same_factual_trace_groups"] += comparison["same_factual_trace"]
            parity_counts["same_actual_call_groups"] += comparison["same_actual_calls"]
            parity_counts["mismatched_draws"] += len(comparison["mismatches"])
            for item in comparison["mismatches"]:
                mismatched_fields.update(item["fields"])
            substantive = (comparison["mismatches"] or not comparison["same_factual_trace"]
                or not comparison["same_actual_calls"] or (comparison["max_absolute_point_difference"] or 0) > 1e-12)
            if substantive:
                parity_counts["budget_control_discrepant_groups" if mechanism.startswith("budget-") else "nonbudget_discrepant_groups"] += 1
            pair_details.append({"trial": trial, **comparison})
        if index in disposition_index and "semantic_digest" in disposition_index[index]:
            disposition_row = disposition_index[index]
            original_group = {key: value for key, value in disposition_row.items() if key != "semantic_digest"}
            original_group["engine_rows"] = rows
            if index in saved_pair_index:
                original_group["comparison"] = {key: value for key, value in saved_pair_index[index].items()
                                                if key != "trial"}
            assert semantic_digest(original_group) == disposition_row["semantic_digest"], (index, "group semantic digest")
            semantic_bindings_checked += 1
        groups.append({"trial": trial, "engine_files": len(rows)})
    actual_paths = {p.relative_to(study).as_posix() for p in (study / "trials").glob("*.json.gz")}
    assert actual_paths <= expected_paths
    if complete:
        assert len(actual_paths) == 2048
        assert seal["trial_files"] == seal["planned_trial_files"] == 2048
    summary = []
    for mechanism in plan["mechanisms"]:
        for method in METHODS:
            for variant in NATIVE_VARIANTS[method] + CX_VARIANTS[method]:
                for position in range(3):
                    # Preserve the complete prospective denominator even for missing engines.
                    reference_values = p["references"][mechanism][method]
                    reference = None if reference_values is None else reference_values[position]
                    key = (mechanism, method, variant, position)
                    summary.append({"mechanism": mechanism, "method": method, "variant": variant,
                                    "position": position, **summary_row(estimates[key], reference, 64)})
    if (study / "summary.json").exists():
        saved = load(study / "summary.json")["rows"]
        saved_index = {(r["mechanism"], r["method"], r["variant"], r["position"]): r for r in saved}
        assert len(saved_index) == len(summary)
        for row in summary:
            key = tuple(row[k] for k in ("mechanism", "method", "variant", "position"))
            expected = saved_index[key]
            for name, value in row.items():
                if type(value) is float:
                    assert_close(value, expected[name], f"summary {key}/{name}")
                else:
                    assert value == expected[name], (key, name, value, expected[name])
    disposition_summary = None
    if (study / "disposition.json").exists():
        disposition = saved_disposition
        assert len(disposition["groups"]) == 1024 and disposition["redraws"] == 0
        assert [g["trial"] for g in disposition["groups"]] == p["trials"]
        assert dict(Counter(g["status"] for g in disposition["groups"])) == disposition["counts"]
        observed = {g["trial"]["group_index"]: g for g in groups}
        for group in disposition["groups"]:
            if group["status"] == "completed":
                assert observed[group["trial"]["group_index"]]["engine_files"] == 2
            if group["status"] == "unstarted":
                assert observed[group["trial"]["group_index"]]["engine_files"] == 0
        disposition_summary = disposition["counts"]
    if (study / "paired-validation.json").exists():
        saved = saved_pairs
        assert len(saved) == len(pair_details)
        indexed = {r["trial"]["group_index"]: r for r in saved}
        for row in pair_details:
            original = indexed[row["trial"]["group_index"]]
            for key in ("same_factual_trace", "same_actual_calls", "draws_compared", "max_absolute_point_difference"):
                assert row[key] == original[key], (row["trial"]["group_index"], key)
            # Trial dictionaries were canonically serialized (sorted keys),
            # whereas the producer's comparison list preserves variant creation
            # order. Match the complete list by variant/position, not order.
            assert sorted(row["point_differences"], key=lambda item: (item["variant"], item["position"])) == sorted(
                original["point_differences"], key=lambda item: (item["variant"], item["position"])), (
                    row["trial"]["group_index"], "point_differences")
            # Producer does not compare inactive_held_indices; check its shared fields separately.
            stripped = [{"slot": r["slot"], "fields": sorted(k for k in r["fields"] if k != "inactive_held_indices")}
                        for r in row["mismatches"]]
            stripped = [r for r in stripped if r["fields"]]
            assert stripped == [{"slot": r["slot"], "fields": sorted(r["fields"])} for r in original["mismatches"]]
    result = {"schema": "independent-upstream-car-artifact-audit-v1",
        "audited_utc": datetime.now(timezone.utc).isoformat(), "final": not provisional,
        "collection_complete": complete, "protocol_sha256": hash_bytes((study / "protocol.json").read_bytes()),
        "auditor_source_sha256": hash_bytes(Path(__file__).read_bytes()),
        "source_revision": p["source_revision"], "upstream_revision": provenance["revision"],
        "manifest_sha256": hash_bytes(terminal.read_bytes()) if terminal.exists() else None,
        "planned_paired_groups": 1024, "planned_engine_trials": 2048,
        "observed_engine_files": len(actual_paths), "group_dispositions": disposition_summary,
        "group_semantic_digest_bindings_checked": semantic_bindings_checked,
        "paired_semantics": dict(parity_counts), "mismatch_fields": dict(mismatched_fields),
        "execution_cost_by_method_engine": [
            {"method": key[0], "engine": key[1], **dict(value)}
            for key, value in sorted(execution_costs.items())],
        "execution_cost_interpretation": {
            "fresh_policy_calls": "Independently recomputed from retained factual decisions and resampled reply receipts; includes factual plus continuation calls.",
            "native_glue_counts": "Aggregated recorded deterministic prefix-reconstruction/probe counters, not fresh stochastic policy calls; full glue event histories are not retained.",
            "cx_world_counts": "Completed replay worlds independently counted from known/unknown retained receipts; a separate full-hold preflight world is recorded per engine trial.",
            "timing": "Sum of trial elapsed times includes adapter glue and concurrent worker contention. This is not serial duration or an intrinsic speed comparison."},
        "engine_disposition_and_cost": [{"mechanism": key[0], "method": key[1], "engine": key[2],
            "planned_engine_trials": 64, **dict(value), "draw_status": dict(draw_dispositions[key])}
            for key, value in sorted(totals.items())],
        "summary": summary, "independent_closed_form_references": references,
        "checks": {"frozen_local_sources_match": True, "pinned_upstream_sources_match": True,
                   "all_observed_raw_schedules_outcomes_points_budgets_checked": True,
                   "reported_summary_and_pair_outputs_match_when_present": True,
                   "no_collection_or_summarizer_imports_or_new_trials": True},
        "limitations": ["In-progress files are provisional until a terminal manifest or incomplete receipt exists.",
            "Simulator/policy/transport compatibility and conditional calibration, not independent tasks or method superiority.",
            "Coverage follows frozen exact floating comparisons; independently derived rational references agree within1e-12.",
            "Intervals are read from recorded engine outputs; this audit independently computes points, coverage, error and widths.",
            "Native CAR budget-control contrastive batches coalesce 31 or32 zero-spend refusal records under one failed canonical slot. The audit admits only the exact pinned gather/bridge shape; known/completed draws remain strict. Native failed/unstarted slot labels do not provide a one-to-one refused-attempt inventory, and these trials have no primary numeric estimates.",
            "Counterfactual full event histories are not retained; their trace hashes cannot be regenerated without replay. This audit checks retained semantic evidence and file bindings."]}
    output.mkdir(parents=True, exist_ok=True)
    stem = f"provisional-{len(actual_paths):04d}" if provisional else "final-audit"
    with (output / f"{stem}.json").open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    lines = ["# Independent CAR artefact audit", "", f"Final audit: {not provisional}; complete collection: {complete}.",
        f"Observed engine files: {len(actual_paths)}/2048. Planned paired groups:1024.", "",
        "Paired semantic counts: `" + json.dumps(dict(parity_counts), sort_keys=True) + "`.",
        "Group dispositions: `" + json.dumps(disposition_summary, sort_keys=True) + "`.", "",
        "Every observed trial was checked against the frozen schedule, complete draw inventory, public readback semantics, actual-call budget, primary missingness gate and independently recomputed point estimate. Closed-form Bernoulli references were derived without replay or importing the collection implementation. Final summaries and pair comparisons were independently recomputed where present.", "",
        "| Mechanism | Method | Variant | Position | Available/64 | Covered/scored | Mean width | Bias | RMSE |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    def fmt(value):
        return "undefined" if value is None else f"{value:.6g}"
    for row in summary:
        lines.append(f"| {row['mechanism']} | {row['method']} | {row['variant']} | {row['position']} | "
            f"{row['available']}/64 | {row['covered']}/{row['scored']} | {fmt(row['mean_width'])} | {fmt(row['bias'])} | {fmt(row['rmse'])} |")
    lines.extend(["", *result["limitations"], ""])
    with (output / f"{stem}.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    return {"status": "provisional" if provisional else "audited_complete" if complete else "audited_incomplete",
            "audit": str(output / f"{stem}.json"), "paired_semantics": dict(parity_counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--provisional", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.study, args.snapshot, args.upstream, args.output, provisional=args.provisional)))


if __name__ == "__main__":
    main()
