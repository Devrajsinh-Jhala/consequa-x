"""Independent stdlib audit of finite refund-interaction evidence.

No Consequa-X imports: reconstruct costs, reachability, readback targets,
population mixture values and permutation-defined Shapley shares directly.
Usage: python scripts/audit_refund_interactions.py OUTPUT_DIRECTORY
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import gzip
from hashlib import sha256
from itertools import permutations
import json
from math import isclose, isfinite
from pathlib import Path, PurePosixPath


TARGETS = ("action", "consequence", "action_linked_consequence")
COMPONENTS = ((False, False), (False, True), (True, False), (True, True))
GAMES = ("strict", "on_reach")
MASS_FIELDS = ("known_mass", "unknown_mass", "invalid_mass", "failed_mass", "unstarted_mass")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise AssertionError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _decode(text):
    return json.loads(text, object_pairs_hook=_pairs,
                      parse_constant=lambda token: (_ for _ in ()).throw(
                          AssertionError("nonfinite JSON constant: " + token)))


def audit(root, expected_source=None):
    root = Path(root).resolve()
    assertions = 0

    def check(condition, message):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(message)

    def numeric(actual, expected, message):
        check(actual is None if expected is None else actual is not None
              and type(actual) in (int, float) and isfinite(actual)
              and isclose(float(actual), float(expected), rel_tol=0, abs_tol=1e-12), message)

    def vector(actual, expected, length, message):
        if expected is None:
            check(actual is None, message + ": whole-vector refusal")
            return
        check(type(actual) is list and len(actual) == length, message + ": complete vector length")
        for index in range(length):
            numeric(actual[index], expected[index], message + f"/{index}")

    def row_key(row, message):
        check(type(row) is dict, message + ": row object")
        check(type(row.get("case")) is str and row["case"] in cases, message + ": known case")
        check(row.get("coalition_game") in GAMES, message + ": explicit game")
        check(type(row.get("component_index")) is int and 0 <= row["component_index"] < 4,
              message + ": Boolean component index")
        role, mask = row.get("record_type"), row.get("mask")
        check((role == "factual" and mask is None) or
              (role == "branch" and type(mask) is int and 0 <= mask < 8),
              message + ": factual or branch mask")
        return (row["case"], row["coalition_game"], row["component_index"], role, mask)

    def load_lines(name):
        with gzip.open(root / name, "rt", encoding="utf-8") as stream:
            return [_decode(line) for line in stream]

    manifest = _decode((root / "manifest.json").read_text(encoding="utf-8"))
    check(type(manifest) is dict, "manifest object")
    check(("artifacts" in manifest) != ("files" in manifest), "exactly one manifest inventory format")
    if "artifacts" in manifest:
        check(manifest.get("status") == "completed", "completion manifest")
        if "completed" in manifest:
            check(manifest["completed"] is True, "completion manifest Boolean")
        check(type(manifest["artifacts"]) is list and bool(manifest["artifacts"]),
              "manifest nonempty artifact list")
        entries = []
        for item in manifest["artifacts"]:
            check(type(item) is dict and set(item) == {"path", "bytes", "sha256"},
                  "manifest exact artifact entry fields")
            entries.append((item["path"], {"bytes": item["bytes"], "sha256": item["sha256"]}))
    else:
        check(manifest.get("completed") is True, "completion manifest")
        if "status" in manifest:
            check(manifest["status"] == "completed", "completion manifest status")
        check(type(manifest["files"]) is dict and bool(manifest["files"]), "manifest nonempty file object")
        entries = list(manifest["files"].items())
    inventory = {p.relative_to(root).as_posix() for p in root.rglob("*")
                 if p.is_file() and p != root/"manifest.json"}
    resolved, names = set(), set()
    for name, item in entries:
        check(type(name) is str, "manifest path string")
        canonical = PurePosixPath(name)
        check(bool(name) and not canonical.is_absolute() and canonical.as_posix() == name
              and all(part not in ("", ".", "..") and ":" not in part and "\\" not in part
                      for part in name.split("/")), "manifest safe canonical relative path")
        path = (root/name).resolve()
        check(path.is_relative_to(root) and path != root/"manifest.json", "manifest contained path")
        check(name not in names and path not in resolved, "manifest unique resolved path")
        names.add(name)
        resolved.add(path)
        check(type(item) is dict and set(item) == {"bytes", "sha256"}, "manifest exact file entry fields")
        check(type(item["bytes"]) is int and item["bytes"] >= 0,
              "manifest nonnegative integer byte size")
        check(type(item["sha256"]) is str and len(item["sha256"]) == 64
              and all(character in "0123456789abcdef" for character in item["sha256"]),
              "manifest SHA256 lowercase hexadecimal string")
        data = path.read_bytes()
        check(len(data) == item["bytes"], "manifest artifact byte size: " + name)
        check(sha256(data).hexdigest() == item["sha256"], "manifest artifact hash: " + name)
    check(inventory == names, "manifest exhaustive inventory")
    protocol = _decode((root / "protocol.json").read_text(encoding="utf-8"))
    summary = _decode((root / "summary.json").read_text(encoding="utf-8"))
    check(type(protocol["source_revision"]) is str and bool(protocol["source_revision"].strip()),
          "declared frozen source identifier")
    if expected_source is not None:
        check(protocol["source_revision"] == expected_source, "expected frozen source identifier")
    cases = protocol["cases"]
    check(type(cases) is dict and bool(cases), "nonempty declared case inventory")
    check(protocol["targets"] == list(TARGETS), "declared target inventory")
    check(protocol["mask_order"] == list(range(8)), "declared full mask order")
    check(type(protocol["schedule"]) is list, "schedule list")
    expected_groups = {(name, game, component) for name in cases for game in GAMES for component in range(4)}
    scheduled = []
    for entry in protocol["schedule"]:
        check(type(entry) is dict and type(entry.get("case")) is str and entry["case"] in cases,
              "schedule known case")
        check(entry.get("coalition_game") in GAMES and type(entry.get("component_index")) is int
              and 0 <= entry["component_index"] < 4, "schedule explicit game/component")
        scheduled.append((entry["case"], entry["coalition_game"], entry["component_index"]))
    check(Counter(scheduled) == Counter(expected_groups), "complete unique case/game/component schedule")
    for name, spec in cases.items():
        check(type(spec) is dict and spec.get("name") == name, "case identity")
        for field in ("selection_probability", "retry_probability"):
            value = spec[field]
            check(type(value) in (int, float) and isfinite(value) and 0 <= value <= 1,
                  "case probability: " + field)
        check(type(spec["use_idempotency"]) is bool and type(spec["include_provenance"]) is bool,
              "case Boolean controls")
        check(type(spec["read_lag_ms"]) is int and spec["read_lag_ms"] >= 0
              and type(spec["max_calls"]) is int and spec["max_calls"] >= 3, "case lag and budget")
    check(type(summary["cases"]) is dict and set(summary["cases"]) == set(cases), "summary exact case inventory")
    check(type(protocol["references"]) is dict and set(protocol["references"]) == set(cases),
          "reference exact case inventory")
    rows, gold_rows = load_lines("evidence.jsonl.gz"), load_lines("evaluator-truth.jsonl.gz")
    expected_rows = {(*key, role, mask) for key in expected_groups
                     for role, mask in (("factual", None), *(("branch", mask) for mask in range(8)))}
    evidence_keys = [row_key(row, "evidence") for row in rows]
    check(Counter(evidence_keys) == Counter(expected_rows), "complete unique evidence record/mask inventory")
    grouped = defaultdict(list)
    gold = {}
    for row in gold_rows:
        key = row_key(row, "gold")
        check(key not in gold, "unique gold key")
        gold[key] = row
    seen, all_keys = set(), set()
    total_calls = 0
    for entry in protocol["schedule"]:
        key = (entry["case"], entry["coalition_game"], entry["component_index"])
        check(key not in seen, "unique schedule group")
        seen.add(key)
        group = [row for row in rows if (row["case"], row["coalition_game"], row["component_index"]) == key]
        check(len(group) == 9 and group[0]["record_type"] == "factual", "one factual plus eight masks")
        spec = protocol["cases"][entry["case"]]
        p, q = Fraction(str(spec["selection_probability"])), Fraction(str(spec["retry_probability"]))
        fresh_select, fresh_retry = COMPONENTS[entry["component_index"]]
        weight = (p if fresh_select else 1 - p) * (q if fresh_retry else 1 - q)
        numeric(entry["component_weight"], weight, "declared component weight")
        check((entry["component_weight"] > 0) == (weight > 0), "declared positive/zero component mass")
        check(type(entry["fresh_selection"]) is bool and type(entry["fresh_retry"]) is bool
              and (entry["fresh_selection"], entry["fresh_retry"]) == (fresh_select, fresh_retry),
              "declared component choices")
        check(type(entry["factual_policy_seed"]) is int and
              4_000_000 <= entry["factual_policy_seed"] <= (2**31-1-5)//6, "disjoint phase window")
        check(entry["factual_world_seed"] == entry["factual_policy_seed"], "factual seed schedule")
        check(type(entry["branch_continuation_seeds_by_mask"]) is list
              and len(entry["branch_continuation_seeds_by_mask"]) == 8
              and all(type(seed) is int and 0 <= seed <= (2**31-1-5)//6
                      for seed in entry["branch_continuation_seeds_by_mask"]), "complete valid continuation seed vector")
        check(entry["max_calls"] == spec["max_calls"], "declared component budget")
        for model_seed in [entry["factual_policy_seed"] * 6 + i for i in range(3)]:
            check(model_seed not in all_keys, "disjoint factual phase seed")
            all_keys.add(model_seed)
        calls = 3
        check(group[0]["policy_calls"] == 3, "factual actual calls")
        for index, row in enumerate(group):
            check(row["policy_metadata"]["fresh_rule"]["kind"] == "deterministic_mixture_component",
                  "honest component metadata")
            check(row["policy_metadata"]["hidden_evidence_inputs"] is False, "public-only metadata")
            check(row["policy_metadata"]["conditioning"]["naturally_sampled_factual"] is False,
                  "planted factual metadata")
            numeric(row["component_weight"], weight, "row weight")
            check((row["component_weight"] > 0) == (weight > 0), "row positive/zero component mass")
            factual = index == 0
            if factual:
                selected, retried, expected_count = True, True, 3
            else:
                mask = index - 1
                check(row["mask"] == mask, "predeclared mask order")
                held = [player for player in range(3) if mask & (1 << player)]
                check(row["held_indices"] == held, "held mask")
                check(row["continuation_seed"] == entry["branch_continuation_seeds_by_mask"][mask],
                      "continuation seed plan")
                for phase in range(3):
                    model_seed = row["continuation_seed"] * 6 + phase
                    check(model_seed not in all_keys, "disjoint continuation phase seed")
                    all_keys.add(model_seed)
                selected = bool(mask & 1) or fresh_select
                retried = selected and (bool(mask & 2) or fresh_retry)
                expected_count = 1 if not selected else 3 if retried else 2
                unreachable = [player for player in held if player >= expected_count]
                cost = sum(player not in held for player in range(expected_count))
                remaining = entry["max_calls"] - calls
                status = ("unstarted" if remaining == 0 else "failed" if cost > remaining else
                          "invalid" if entry["coalition_game"] == "strict" and unreachable else "completed")
                check(row["status"] == status, "budget/reachability status")
                check(type(row["bad_targets"]) is dict and set(row["bad_targets"]) == set(TARGETS),
                      "complete branch target inventory")
                actual_cost = 0 if status == "unstarted" else min(cost, remaining)
                check(row["policy_calls"] == actual_cost, "actual branch calls")
                calls += actual_cost
                check(row["budget_calls_after"] == calls, "cumulative budget counter")
                inactive = unreachable if entry["coalition_game"] == "on_reach" and status == "completed" else []
                check(row["inactive_held_indices"] == inactive, "normal termination inactivity")
                check(sum(item["policy_calls"] for item in row["decisions"]) == actual_cost,
                      "receipt call sum")
                for player, receipt in enumerate(row["decisions"]):
                    check(receipt["index"] == player, "receipt positions contiguous")
                    check(receipt["continuation_model_seed"] == row["continuation_seed"] * 6 + player,
                          "receipt model phase key")
                    check(receipt["source"] == ("held_factual" if player in held else "resampled"),
                          "receipt source")
                grouped[(entry["case"], entry["coalition_game"], mask)].append(row)
                if status != "completed":
                    check(row["trace"] is None and all(value is None for value in row["bad_targets"].values()),
                          "no fabricated failed or invalid outcome")
                    continue
            trace = row["trace"]
            decisions = [event for event in trace["events"] if event["type"] == "agent_decision"]
            operations = [event["data"]["policy_reply"]["decision"]["operation"] for event in decisions]
            expected_operations = ["stop"] if not selected else ["refund", "retry", "stop"] if retried else ["refund", "stop"]
            check(operations == expected_operations and len(decisions) == expected_count, "actual operations")
            observation, action = trace["observations"][-1], trace["action"]
            contract = action["contract"]
            horizon = contract["deadline_ms"] + contract["stability_ms"]
            qualifies = [record for record in observation["records"]
                if record["payment_id"] == contract["expected"]["payment_id"]
                and record["amount_minor"] == contract["expected"]["amount_minor"]
                and record["currency"] == contract["expected"]["currency"]
                and action["registered_at_ms"] <= record["committed_at_ms"] <= contract["deadline_ms"]
                and record["status"] == "processed"]
            known = observation["complete"] and observation["available"] and observation["as_of_ms"] >= horizon
            consequence_bad = int(len(qualifies) != 1) if known else None
            linked_bad = (None if consequence_bad is None else 1 if consequence_bad else
                          0 if any(record.get("action_id") == action["action_id"]
                                   and record.get("actor") == action["actor"] for record in qualifies) else None)
            bad = dict(zip(TARGETS, (int(not selected), consequence_bad, linked_bad)))
            if not factual:
                check(row["bad_targets"] == bad, "independent public readback targets")
            expected_verification = "unknown" if consequence_bad is None else "violated" if consequence_bad else "satisfied"
            check(trace["verifications"][-1]["status"] == expected_verification, "verification independently reproduced")
            gold_key = (*key, row["record_type"], row.get("mask"))
            check(gold_key in gold, "completed episode has separate evaluator gold")
            gold_row = gold.pop(gold_key)
            refunds = [record for record in gold_row["records"] if record["kind"] == "refund"]
            expected_refunds = int(selected) * (1 + int(retried and not spec["use_idempotency"]))
            check(len(refunds) == expected_refunds, "actual payment effects in gold")
            projected = []
            for record in refunds:
                if record["committed_at_ms"] > observation["as_of_ms"]:
                    continue
                public = {key: value for key, value in record.items() if key != "kind"
                          and (spec["include_provenance"] or key not in ("actor", "action_id", "attempt_id"))}
                projected.append(public)
            check(observation["records"] == projected, "readback is the actual bounded gold projection")
            attempts = [record for record in gold_row["records"] if record["kind"] == "execution_attempt"]
            check(len(attempts) == int(selected) + int(retried), "actual payment attempts")
            check(gold_row["seed"] == entry["factual_world_seed"], "reset original payment world")
        total_calls += calls
    check(not gold, "no extra evaluator gold")
    check(len(rows) == len(protocol["schedule"]) * 9, "complete evidence inventory")
    check(summary["actual_policy_calls"] == total_calls, "global actual calls")
    check(summary["completed"] is True and summary["additional_reference_policy_calls"] == 0,
          "completed enumeration with no reference calls")
    for name, spec in protocol["cases"].items():
        check(set(summary["cases"][name]["games"]) == set(GAMES), "summary exact game inventory")
        check(set(protocol["references"][name]) == set(GAMES), "reference exact game inventory")
        check(summary["cases"][name]["actual_policy_calls"] == sum(row["policy_calls"] for row in rows
              if row["case"] == name), "per-case actual calls")
        for game in GAMES:
            reported = summary["cases"][name]["games"][game]
            check(set(reported["targets"]) == set(TARGETS), "summary exact target inventory")
            reference_game = protocol["references"][name][game]
            check(reported["reference"] == reference_game, "summary matches declared population reference")
            check(reference_game["name"] == name and reference_game["coalition_game"] == game
                  and reference_game["decision_count"] == 3, "reference case/game/player identity")
            check(set(reference_game["targets"]) == set(TARGETS), "reference exact target inventory")
            check(type(reference_game["coalition_valid_probabilities"]) is list
                  and len(reference_game["coalition_valid_probabilities"]) == 8, "reference validity vector length")
            all_branches = [row for row in rows if row["case"] == name and row["coalition_game"] == game
                            and row["record_type"] == "branch"]
            expected_statuses = {status: sum(row["status"] == status for row in all_branches)
                                 for status in ("completed", "invalid", "failed", "unstarted")}
            check(reported["branch_status_counts"] == expected_statuses, "independent branch status counts")
            check(reported["inactive_held_branch_count"] == sum(bool(row["inactive_held_indices"])
                  for row in all_branches), "independent inactive held branch count")
            p, q = Fraction(str(spec["selection_probability"])), Fraction(str(spec["retry_probability"]))
            weights = tuple((p if selected else 1-p) * (q if retry else 1-q)
                            for selected, retry in COMPONENTS)
            for target in TARGETS:
                result = reported["targets"][target]
                check(type(result["coalition_bad_rates"]) is list and len(result["coalition_bad_rates"]) == 8,
                      "reported coalition vector length")
                check(type(result["mass_by_mask"]) is list and len(result["mass_by_mask"]) == 8,
                      "reported mask mass vector length")
                reference = reference_game["targets"][target]
                check(type(reference["coalition_bad_rates"]) is list and len(reference["coalition_bad_rates"]) == 8,
                      "reference coalition vector length")
                check(type(reference["unknown_probabilities"]) is list and len(reference["unknown_probabilities"]) == 8,
                      "reference unknown vector length")
                check(reference["shapley_values"] is None or
                      type(reference["shapley_values"]) is list and len(reference["shapley_values"]) == 3,
                      "reference coefficient vector length")
                values = []
                for mask in range(8):
                    component_rows = grouped[(name, game, mask)]
                    check(Counter(row["component_index"] for row in component_rows) == Counter(range(4)),
                          "complete mask component inventory including zero weights")
                    positive = [row for row in component_rows if weights[row["component_index"]] > 0]
                    expected = (None if any(row["status"] != "completed" or row["bad_targets"][target] is None
                                           for row in positive) else
                        sum(weights[row["component_index"]] * row["bad_targets"][target] for row in positive))
                    values.append(expected)
                    numeric(result["coalition_bad_rates"][mask], expected, "weighted coalition rate")
                    masses = result["mass_by_mask"][mask]
                    check(type(masses) is dict and set(masses) == set(MASS_FIELDS), "complete status mass inventory")
                    expected_mass = dict.fromkeys(MASS_FIELDS, Fraction(0))
                    for row in component_rows:
                        status = row["status"]
                        field = ("unknown_mass" if row["bad_targets"][target] is None else "known_mass") \
                            if status == "completed" else status + "_mass"
                        expected_mass[field] += weights[row["component_index"]]
                    for field in MASS_FIELDS:
                        numeric(masses[field], expected_mass[field], "independent status mass: " + field)
                    numeric(sum(masses.values()), 1, "complete population mass")
                shares = None
                if all(value is not None for value in values):
                    shares = [Fraction(0)] * 3
                    for order in permutations(range(3)):
                        mask = 0
                        for player in order:
                            shares[player] += (values[mask | (1 << player)] - values[mask]) / 6
                            mask |= 1 << player
                vector(result["shapley_values"], shares, 3, "permutation-defined coefficient")
                check(type(result["numeric_available"]) is bool and result["numeric_available"] == (shares is not None),
                      "whole-vector numeric availability")
                endpoint = values[7] - values[0] if values[7] is not None and values[0] is not None else None
                numeric(reported["targets"][target]["endpoint_difference"], endpoint, "endpoint total")
                interaction = values[3] - values[1] - values[2] + values[0] if all(values[i] is not None for i in (0, 1, 2, 3)) else None
                numeric(reported["targets"][target]["selection_retry_interaction"], interaction, "interaction contrast")
                if name != "budget-p50-q50":
                    vector(reference["coalition_bad_rates"], values, 8,
                           "independent population reference matches physical game")
                    vector(reference["shapley_values"], shares, 3, "reference coefficient independently reproduced")
                    check(type(reference["shapley_eligible"]) is bool and
                          reference["shapley_eligible"] == (shares is not None), "reference whole-game eligibility")
                    check(type(reference["endpoint_eligible"]) is bool and
                          reference["endpoint_eligible"] == (endpoint is not None), "reference endpoint eligibility")
                    numeric(reference["endpoint_difference"], endpoint, "reference endpoint independently reproduced")
                    # Population interaction is numerical only when the full
                    # game is eligible; the four-mask diagnostic may remain
                    # numerical for an otherwise undefined strict game.
                    numeric(reference["selection_retry_interaction"], interaction if shares is not None else None,
                            "reference interaction independently reproduced")
    return {"passed": True, "assertions": assertions, "case_count": len(protocol["cases"]),
            "planned_branches": len(protocol["schedule"]) * 8, "actual_policy_calls": total_calls,
            "source_revision": protocol["source_revision"],
            "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "auditor_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "manifest_files_checked": len(entries),
            "manifest_sha256": sha256((root/"manifest.json").read_bytes()).hexdigest(),
            "auditor": "stdlib independent raw readback, costs, mixture and six-permutation calculation"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--expected-source")
    args = parser.parse_args()
    print(json.dumps(audit(args.output, args.expected_source), indent=2, sort_keys=True))
