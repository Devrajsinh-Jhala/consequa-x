"""Descriptive analysis of the sealed, independently audited LIMBO matrix.

No model, network, native task construction, package execution or gold regrading
occurs here. A passed audit can contain failures and unavailable grades. The
all-planned endpoint counts only audited true native grades in its numerator;
unavailable grades remain unavailable, rather than becoming semantic failures.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import re
import statistics
import subprocess


ARMS = ("vanilla", "sdk_retry3", "guard", "conseqax_guard")
ARM_LABELS = ("Vanilla", "SDK retry", "Native guard", "ConseqaX guard")
PIN = "2db09fba22a0572a70639162a808906409f612a8"
MODES = ("timeout_pre", "timeout_post", "timeout_late", "timeout_late_tail",
         "partial_timeout", "duplicate_delivery")
GRADE_BOOL = ("TS", "EOS", "clean_success", "exact_state")
GRADE_COUNTS = ("dup_executed", "dup_live", "dup_compensated",
                "extraneous_writes", "n_effects")
MODEL_COUNTS = ("model_invocations", "model_completions", "model_dispatches",
                "model_cap_refusals", "receipt_count")
USAGE = ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def binding(path):
    data = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def load(path):
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON object key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=reject_duplicate,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON: " + value)))


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True).stdout


def nonnegative(value, label, *, integer=True):
    require(type(value) is int if integer else type(value) in (int, float),
            label + " has an invalid numeric type")
    require(value >= 0 and math.isfinite(value), label + " is negative/non-finite")


def registered_schedule(protocol):
    """Reconstruct the metadata-only selection independently of the collector."""
    metadata, seed = protocol["metadata"], protocol["seed"]
    require(len(metadata) == 12, "The registered study has exactly 12 base templates")
    require(len({item["template"] for item in metadata}) == 12, "Duplicate template metadata")
    require(all(type(item["index"]) is int and item["index"] > 1 for item in metadata),
            "Development indices cannot enter the measured matrix")
    templates = sorted(metadata, key=lambda item: digest([seed, item["template"], item["index"]]))
    candidates = []
    for item in templates:
        for focal in item["focals"]:
            for mode in MODES:
                if mode == "partial_timeout" and not focal["batch"]:
                    continue
                candidates.append({"template": item["template"], "index": item["index"],
                    "focal": focal["label"], "mode": mode, "family": item["family"],
                    "domain": focal["domain"], "affordances": {key: focal[key] for key in
                        ("batch", "verification", "idempotency", "reversible")}})
    batch = [item for item in templates if any(focal["batch"] for focal in item["focals"])]
    reserved = min(batch, key=lambda item: digest([seed, "partial-slot", item["template"]]))["template"] if batch else None
    selected, counts = [], Counter()
    for item in templates:
        available = [row for row in candidates if row["template"] == item["template"]]
        if item["template"] == reserved:
            available = [row for row in available if row["mode"] == "partial_timeout"]
        require(bool(available), "Template lacks a compatible registered fault")
        chosen = min(available, key=lambda row: (counts[row["mode"]],
            sum(world["domain"] == row["domain"] for world in selected), digest([seed, row])))
        selected.extend(({**chosen, "mode": "none"}, chosen))
        counts[chosen["mode"]] += 1
    require({row["domain"] for row in selected} == {"billing", "data", "deploy", "mail", "social", "tickets"},
            "The measured schedule must cover all six registered focal domains")
    require(set(counts) == set(MODES), "Registered fault coverage differs")
    tool_cap = protocol["schedule"][0]["spec"]["max_tool_calls"]
    result = []
    for rank, world in enumerate(selected):
        order = ARMS[rank % 4:] + ARMS[:rank % 4]
        for arm in order:
            spec = {key: world[key] for key in ("template", "index", "focal", "mode")}
            spec.update(model=protocol["runtime_binding"]["model"], policy=arm,
                human_available=False, contract="native", max_tool_calls=tool_cap,
                experiment="conseqax-limbo-frozen-v1", paraphrase=0, replicate=0,
                doc_variant="neutral", harness="minimal", instruction_variant="default",
                reasoning_effort=None)
            result.append({"slot": len(result), "world_rank": rank, "arm": arm,
                           "metadata": world, "spec": spec})
    return result


def validate_row(row, planned):
    require(all(row.get(key) == planned[key] and type(row.get(key)) is type(planned[key])
                for key in ("slot", "world_rank", "arm")), "Audit slot identity/order differs")
    for key in ("started", "operational", "audit_complete", "grade_available", "execution_success"):
        require(type(row.get(key)) is bool, "Audit availability flag is not boolean: " + key)
    available = row["operational"]
    require(available == row["audit_complete"] == row["grade_available"],
            "Audit grade/replay availability flags disagree")
    if not available:
        require(row.get("native_grade") is None and not row["execution_success"],
                "Unavailable native grade was replaced by a value")
        require(row["status"] not in ("audited_native_return", "audited_native_error_return"),
                "Unavailable grade has an audited-return disposition")
        if not row["started"]:
            require(row["status"].startswith("unstarted"), "Unstarted slot disposition differs")
        return
    require(row["started"], "An unstarted slot has an audited grade")
    expected_status = "audited_native_return" if row["execution_success"] else "audited_native_error_return"
    require(row["status"] == expected_status, "Native return/error disposition differs")
    require(type(row.get("native_stop_reason")) is str and
            (row.get("native_error") is None or type(row.get("native_error")) is str),
            "Native stop/error availability differs")
    require(row["execution_success"] == (row["native_error"] is None and
            row["native_stop_reason"] not in ("llm_error", "harness_error")),
            "Execution success disagrees with native stop/error")
    grade = row.get("native_grade")
    require(type(grade) is dict, "Native grade is missing")
    for key in GRADE_BOOL:
        require(type(grade.get(key)) is bool, "Native grade is not boolean: " + key)
    for key in GRADE_COUNTS:
        nonnegative(grade.get(key), "Native " + key)
    require(type(grade.get("collateral")) is list, "Native collateral must remain a list")
    require(grade["EOS"] == (grade["TS"] and grade["dup_executed"] == 0), "Native EOS definition differs")
    require(grade["clean_success"] == (grade["TS"] and grade["dup_live"] == 0), "Native clean-success definition differs")
    require(type(row.get("fault_triggered")) is bool, "Fault trigger availability differs")
    require(type(row.get("package_same_native_guard_replay")) is bool
            and row["package_same_native_guard_replay"] == (row["arm"] == "conseqax_guard"),
            "Package/native guard replay conformance flag differs")
    for key in MODEL_COUNTS:
        nonnegative(row.get(key), key)
    require(row["model_completions"] <= row["model_dispatches"] <= row["model_invocations"],
            "Model dispatch/completion counts disagree")
    require(row["model_cap_refusals"] <= 1, "Too many combined-cap refusals")
    require(row["receipt_count"] == 0 or row["arm"] == "conseqax_guard", "Comparator emitted SDK receipts")
    require(type(row.get("work")) is dict and set(row["work"]) <= {"execute", "verify", "advance", "flush"},
            "Boundary work inventory differs")
    for key, value in row["work"].items():
        nonnegative(value, "Boundary " + key)
    charges = row.get("work_charges", {})
    for key in ("native_tool_events", "public_verify_attempts", "outer_wait_attempts", "flush_attempts"):
        nonnegative(charges.get(key), key)
    nonnegative(charges.get("outer_virtual_wait_seconds"), "outer_virtual_wait_seconds", integer=False)
    require(charges.get("boundary_enter_counts_are_not_physical_effect_counts") is True,
            "Boundary/effect distinction is missing")
    require(charges["public_verify_attempts"] == row["work"].get("verify", 0)
            and charges["flush_attempts"] == row["work"].get("flush", 0)
            and charges["outer_wait_attempts"] <= row["work"].get("advance", 0),
            "Wait/verification/flush accounting differs")
    if row["arm"] == "conseqax_guard":
        require(row["receipt_count"] == charges["public_verify_attempts"], "Receipt/public verification count differs")
    for key in ("wall_s", "virtual_seconds"):
        nonnegative(row.get(key), key, integer=False)
    require(type(row.get("usage")) is dict and set(row["usage"]) == set(USAGE), "Token usage inventory differs")
    for key in USAGE:
        usage = row["usage"][key]
        nonnegative(usage.get("observed_prefix_total"), key)
        nonnegative(usage.get("unknown_invocations"), key + " unknown count")
        require(usage["unknown_invocations"] <= row["model_invocations"], "Unknown usage count exceeds invocations")
        require(type(usage.get("complete_for_all_invocations")) is bool
                and usage["complete_for_all_invocations"] == (usage["unknown_invocations"] == 0),
                "Token availability flag differs")


def validate_inputs(audit_path, protocol_path, commit):
    require(bool(re.fullmatch("[0-9a-f]{40}", commit)), "An explicit exact 40-character protocol commit is required")
    audit_path, protocol_path = Path(audit_path).resolve(), Path(protocol_path).resolve()
    if audit_path.is_dir():
        audit_path /= "audit-result.json"
    directory = audit_path.parent
    manifest_path = directory / "manifest.json"
    manifest = load(manifest_path)
    actual = {str(path.relative_to(directory)).replace("\\", "/")
              for path in directory.rglob("*") if path.is_file() and path != manifest_path}
    require(set(manifest) == actual == {audit_path.name}, "Sealed audit inventory differs")
    require(manifest[audit_path.name] == binding(audit_path), "Audit content differs from its sealed manifest")
    root = Path(git(protocol_path.parent, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    relative = protocol_path.relative_to(root).as_posix()
    blob = git(root, "show", f"{commit}:{relative}")
    require(blob == protocol_path.read_bytes(), "Protocol bytes differ from the explicit Git commit")
    protocol, audit = load(protocol_path), load(audit_path)
    require(manifest[audit_path.name] == binding(audit_path), "Audit changed while reading")
    require(blob == protocol_path.read_bytes(), "Protocol changed while reading")
    require(protocol.get("schema") == "conseqax-limbo-protocol-v1"
            and protocol.get("native", {}).get("commit") == PIN, "Unsupported protocol/native pin")
    require(protocol.get("arms") == list(ARMS), "Registered arms differ")
    require(audit.get("schema") == "conseqax-limbo-audit-v1" and audit.get("passed") is True,
            "A passed official collection audit is required")
    require(audit.get("protocol_commit") == commit and audit.get("protocol") == binding(protocol_path),
            "Audit/protocol byte or commit binding differs")
    for value in (audit.get("collection_manifest"),):
        require(type(value) is dict and set(value) == {"sha256", "bytes"}
                and bool(re.fullmatch("[0-9a-f]{64}", value["sha256"]))
                and type(value["bytes"]) is int and value["bytes"] > 0, "Collection manifest binding is missing")
    sources = protocol.get("sources")
    require(type(sources) is dict and bool(sources), "Scientific source binding is empty")
    for name, expected in sources.items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe scientific source path")
        data = git(root, "show", f"{commit}:{name}")
        require(expected == {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)},
                "Scientific source differs from the frozen protocol commit: " + name)
    schedule = protocol.get("schedule")
    require(type(schedule) is list and len(schedule) == 96, "All 96 planned slots must remain in the protocol")
    require(canonical(schedule) == canonical(registered_schedule(protocol)), "Schedule differs from the registered selection")
    rows = audit.get("rows")
    require(type(rows) is list and len(rows) == 96, "Audit omits planned slots")
    for row, planned in zip(rows, schedule):
        validate_row(row, planned)
    scope = audit.get("scope", {})
    for key in ("independent_native_policy_and_effect_replay",
                "conseqax_guard_replayed_as_declared_native_guard",
                "SDK_receipt_current_public_report_mapping_recomputation",
                "saved_context_render_token_proof_consistency"):
        require(scope.get(key) is True, "Required independent audit scope is missing: " + key)
    for key in ("SDK_execution_or_independent_service_verifier_replay",
                "independent_tokenizer_reconstruction", "human_or_network_used",
                "passed_means_all_slots_operational_or_successful"):
        require(scope.get(key) is False, "Audit declared non-claim differs: " + key)
    return protocol, audit, {"audit": {"path": str(audit_path), **binding(audit_path)},
        "audit_manifest": {"path": str(manifest_path), **binding(manifest_path)},
        "protocol": {"path": str(protocol_path), **binding(protocol_path)},
        "protocol_commit": commit, "collection_manifest": audit["collection_manifest"]}


def numeric_summary(values, planned):
    observed = [value for value in values if value is not None]
    return {"observed_total": sum(observed), "rows_available": len(observed),
            "rows_unavailable": planned - len(observed),
            "complete_for_all_planned_slots": len(observed) == planned,
            "mean_among_available": statistics.mean(observed) if observed else None,
            "median_among_available": statistics.median(observed) if observed else None,
            "minimum_observed": min(observed) if observed else None,
            "maximum_observed": max(observed) if observed else None}


def summarize(rows):
    n = len(rows)
    available = [row for row in rows if row["operational"]]
    result = {"planned": n, "started": sum(row["started"] for row in rows),
        "audited_grade_available": len(available), "grade_unavailable": n - len(available),
        "receipt_episodes_with_at_least_one": sum(row.get("receipt_count", 0) >= 1 for row in available),
        "execution_success": sum(row["execution_success"] for row in rows),
        "audited_native_error_returns": sum(row["operational"] and not row["execution_success"] for row in rows),
        "dispositions": dict(sorted(Counter(row["status"] for row in rows).items())),
        "fault_triggered": {"true": sum(row.get("fault_triggered") is True for row in rows),
            "false": sum(row.get("fault_triggered") is False for row in rows),
            "unavailable": sum("fault_triggered" not in row for row in rows)}, "endpoints": {}}
    for key in GRADE_BOOL:
        true = sum(row["native_grade"][key] for row in available)
        result["endpoints"][key] = {"true_audited": true, "false_audited": len(available) - true,
            "grade_unavailable": n - len(available), "planned_denominator": n,
            "all_planned_success_fraction": true / n if n else None,
            "available_grade_success_fraction": true / len(available) if available else None}
    costs = {}
    for key in MODEL_COUNTS + ("wall_s", "virtual_seconds"):
        costs[key] = numeric_summary([row.get(key) if row["operational"] else None for row in rows], n)
    for key in ("execute", "verify", "advance", "flush"):
        costs["boundary_" + key + "_attempts"] = numeric_summary(
            [row["work"].get(key, 0) if row["operational"] else None for row in rows], n)
    for key in ("native_tool_events", "public_verify_attempts", "outer_wait_attempts",
                "outer_virtual_wait_seconds", "flush_attempts"):
        costs[key] = numeric_summary([row["work_charges"][key] if row["operational"] else None for row in rows], n)
    result["costs"] = costs
    result["native_effects"] = {key: numeric_summary(
        [row["native_grade"][key] if row["operational"] else None for row in rows], n)
        for key in GRADE_COUNTS}
    result["native_effects"]["collateral_records"] = numeric_summary(
        [len(row["native_grade"]["collateral"]) if row["operational"] else None for row in rows], n)
    result["usage"] = {}
    for key in USAGE:
        chosen = [row["usage"][key] for row in available]
        unknown = sum(item["unknown_invocations"] for item in chosen)
        result["usage"][key] = {"observed_token_total": sum(item["observed_prefix_total"] for item in chosen),
            "unknown_invocations_among_audited_rows": unknown,
            "known_invocations_among_audited_rows": sum(row["model_invocations"] for row in available) - unknown,
            "audited_rows_with_complete_usage": sum(item["complete_for_all_invocations"] for item in chosen),
            "rows_without_audited_accounting": n - len(available),
            "complete_for_all_planned_slots": len(available) == n and unknown == 0}
    return result


def contrasts(rows):
    worlds = defaultdict(dict)
    for row in rows:
        worlds[row["world_rank"]][row["arm"]] = row
    result = {}
    for left, right in combinations(ARMS, 2):
        item = {"left": left, "right": right, "planned_worlds": len(worlds), "endpoints": {}}
        for metric in ("TS", "EOS"):
            both = [(arms[left], arms[right]) for arms in worlds.values()
                    if arms[left]["operational"] and arms[right]["operational"]]
            left_primary = sum(arms[left]["operational"] and bool((arms[left]["native_grade"] or {}).get(metric))
                               for arms in worlds.values())
            right_primary = sum(arms[right]["operational"] and bool((arms[right]["native_grade"] or {}).get(metric))
                                for arms in worlds.values())
            diffs = [int(a["native_grade"][metric]) - int(b["native_grade"][metric]) for a, b in both]
            item["endpoints"][metric] = {"left_all_planned_true": left_primary,
                "right_all_planned_true": right_primary,
                "all_planned_numerator_difference_left_minus_right": left_primary - right_primary,
                "all_planned_fraction_difference_left_minus_right": (left_primary - right_primary) / len(worlds),
                "both_grades_available": len(both), "at_least_one_grade_unavailable": len(worlds) - len(both),
                "left_only_true_among_both_available": diffs.count(1),
                "right_only_true_among_both_available": diffs.count(-1),
                "same_boolean_among_both_available": diffs.count(0)}
        both = [(arms[left], arms[right]) for arms in worlds.values()
                if arms[left]["operational"] and arms[right]["operational"]]
        getters = {key: (lambda row, field=key: row[field]) for key in
                   ("model_invocations", "model_dispatches", "wall_s", "virtual_seconds")}
        getters.update({"boundary_execute_attempts": lambda row: row["work"].get("execute", 0),
            "public_verify_attempts": lambda row: row["work_charges"]["public_verify_attempts"],
            "outer_wait_attempts": lambda row: row["work_charges"]["outer_wait_attempts"],
            "outer_virtual_wait_seconds": lambda row: row["work_charges"]["outer_virtual_wait_seconds"]})
        item["paired_cost_differences"] = {}
        for key, getter in getters.items():
            differences = [getter(a) - getter(b) for a, b in both]
            item["paired_cost_differences"][key] = {
                "both_accounting_available": len(both),
                "at_least_one_accounting_unavailable": len(worlds) - len(both),
                "observed_sum_left_minus_right": sum(differences),
                "mean_left_minus_right_among_both_available": statistics.mean(differences) if differences else None,
                "median_left_minus_right_among_both_available": statistics.median(differences) if differences else None}
        result[left + "__vs__" + right] = item
    return result


def analyze(protocol, audit, inputs):
    rows = audit["rows"]
    enriched = [{**row, "metadata": planned["metadata"]} for row, planned in zip(rows, protocol["schedule"])]
    strata = {}
    for axis in ("template", "domain", "mode", "family", "condition"):
        groups = defaultdict(list)
        for row in enriched:
            key = ("clean" if row["metadata"]["mode"] == "none" else "assigned_fault") if axis == "condition" else row["metadata"][axis]
            groups[key].append(row)
        strata[axis] = {name: {"arms": {arm: summarize([row for row in group if row["arm"] == arm]) for arm in ARMS},
                             "matched_contrasts": contrasts(group)} for name, group in sorted(groups.items())}
    worlds = []
    for rank in range(24):
        chosen = [row for row in enriched if row["world_rank"] == rank]
        worlds.append({"world_rank": rank, "metadata": chosen[0]["metadata"],
            "arms": {row["arm"]: {"slot": row["slot"], "status": row["status"],
                "grade_available": row["operational"], "execution_success": row["execution_success"],
                "TS": row["native_grade"]["TS"] if row["operational"] else None,
                "EOS": row["native_grade"]["EOS"] if row["operational"] else None} for row in chosen}})
    return {"schema": "conseqax-limbo-analysis-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs, "audit_scope": audit["scope"],
        "planned_slots": 96, "planned_worlds": 24, "base_instances": 12,
        "templates": 12, "focal_domains": 6, "arm_order": list(ARMS),
        "arms": {arm: summarize([row for row in enriched if row["arm"] == arm]) for arm in ARMS},
        "strata": strata, "matched_contrasts": contrasts(enriched), "worlds": worlds,
        "interpretation": [
            "This is a finite purposeful coverage matrix: 12 base instances, 24 task/fault conditions and four arms; 96 slots are not independent tasks.",
            "Primary TS/EOS numerators count only independently replayed true native grades over every planned slot. Missing grades remain unknown, and do not count as success.",
            "Operational means audited native-grade availability, including error returns after native flush; execution_success is a separate secondary endpoint.",
            "Comparisons are paired within the same native world. Clean/fault base parameters match, but native random seeds depend on mode; clean/fault worlds are not identical random worlds.",
            "Strata use assigned faults, never post-treatment fault triggering. Template and domain variation are descriptive; no task-population intervals, significance, equivalence or superiority inference is made.",
            "The ConseqaX arm is an actual receipt integration of the same native guard. Declared policy conformance supports integration, not independent algorithmic novelty or proof that separately generated trajectories must coincide.",
            "Native EOS is TS and zero recorded duplicate executions, not universal exactly-once. Native upsert/status accounting and target scope can hide some repeat writes; exact_state checks target live counts only.",
            "Native dup_compensated is max(0, dup_executed minus dup_live), not a count of compensation calls. Extraneous writes and collateral records are reported separately from EOS.",
            "Boundary execute/verify/advance/flush entries count attempted calls, not physical effects. Advance includes nested tool latency; only outer advances count explicit policy wait attempts.",
            "Native virtual time and observed host wall time are separate descriptive costs. This serial local run does not identify a general runtime-speed advantage.",
            "Cost sums cover rows with audited complete accounting. Failed/unstarted slots can have additional unquantified observed-prefix work; missing actual work is not zero.",
            "Token sums retain known usage even on failed invocations. Missing usage stays unknown; cached input tokens are a subset of input tokens and are never added twice.",
            "SDK receipts verify current native public reports with unknown origin; they do not establish production service durability, settlement or causal responsibility.",
            "The independent audit recomputes receipt contents and replays the unchanged native guard and effects. It does not independently re-execute the SDK or reconstruct tokenizer identities from scratch.",
            "No humans, paid inference or GitHub Actions were used in this analysis."]}


def markdown(result):
    lines = ["# Audited external LIMBO results", "", f"Protocol commit: `{result['inputs']['protocol_commit']}`.",
        "", "12 base instances; 24 task/fault conditions; four arms; 96 planned slots.", "",
        "| Arm | Planned | Grades available | Error returns | TS true/planned | EOS true/planned | Missing grades |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm, label in zip(ARMS, ARM_LABELS):
        row = result["arms"][arm]
        lines.append(f"| {label} | {row['planned']} | {row['audited_grade_available']} | {row['audited_native_error_returns']} | "
                     f"{row['endpoints']['TS']['true_audited']}/{row['planned']} | {row['endpoints']['EOS']['true_audited']}/{row['planned']} | {row['grade_unavailable']} |")
    lines += ["", "All-planned numerators retain missing/error dispositions. An error return can still have an audited physical grade after native flush.",
        "", "| Arm | Execute attempts | Public verifications | Explicit waits | Model dispatches | Rows with complete work accounting |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for arm, label in zip(ARMS, ARM_LABELS):
        row = result["arms"][arm]
        costs = row["costs"]
        values = [costs[key]["observed_total"] for key in
                  ("boundary_execute_attempts", "public_verify_attempts", "outer_wait_attempts", "model_dispatches")]
        lines.append(f"| {label} | " + " | ".join(map(str, values)) + f" | {row['audited_grade_available']}/{row['planned']} |")
    lines += ["", "Observed cost totals exclude unquantified work in rows without complete audited accounting. Boundary advances are not policy waits.",
              "", "## Matched within-world EOS contrasts", "",
              "| Left − right | Planned numerator difference | Both grades available | Left-only true | Right-only true | At least one unknown |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for item in result["matched_contrasts"].values():
        value = item["endpoints"]["EOS"]
        lines.append(f"| {item['left']} − {item['right']} | {value['all_planned_numerator_difference_left_minus_right']} | "
            f"{value['both_grades_available']} | {value['left_only_true_among_both_available']} | "
            f"{value['right_only_true_among_both_available']} | {value['at_least_one_grade_unavailable']} |")
    lines += ["", "## Scope and limitations", ""] + ["- " + note for note in result["interpretation"]]
    return "\n".join(lines) + "\n"


def latex(result):
    lines = ["% Generated from a sealed passed official audit; do not edit values by hand.",
        "% Native EOS is domain-qualified; all-planned denominators include unavailable grades.",
        r"\begin{tabular}{lrrrrr}", r"\hline", r"Arm & $n$ & Graded & TS & EOS & Missing \\", r"\hline"]
    for arm, label in zip(ARMS, ARM_LABELS):
        row = result["arms"][arm]
        lines.append(f"{label} & {row['planned']} & {row['audited_grade_available']} & "
            f"{row['endpoints']['TS']['true_audited']} & {row['endpoints']['EOS']['true_audited']} & {row['grade_unavailable']} " + r"\\")
    lines.extend((r"\hline", r"\end{tabular}", ""))
    return "\n".join(lines)


def narrative(result):
    """Factual manuscript paragraphs computed only from validated audit rows."""
    arms = result["arms"]
    available = sum(row["audited_grade_available"] for row in arms.values())
    errors = sum(row["audited_native_error_returns"] for row in arms.values())
    paragraphs = [
        "The frozen external matrix comprised 12 base instances from 12 templates across six focal domains, "
        "each in a clean condition and one compatible assigned fault condition. Four arms produced 96 planned "
        "slots on 24 matched native worlds. These are 12 base instances, not 96 independent tasks. "
        f"Independent replay established native grades for {available}/96 slots, including {errors} native "
        f"error returns after native settlement; {96 - available} grades were unavailable. "
        "An audited error return remains eligible for the physical endpoint; normal execution success is reported separately."]
    outcomes = []
    for arm, label in zip(ARMS, ARM_LABELS):
        row = arms[arm]
        outcomes.append(f"{label}: TS {row['endpoints']['TS']['true_audited']}/24, "
            f"EOS {row['endpoints']['EOS']['true_audited']}/24, "
            f"{row['audited_grade_available']}/24 grades available and "
            f"{row['execution_success']}/24 normal execution returns")
    paragraphs.append("All-planned native results were " + "; ".join(outcomes) + ". "
        "Only independently audited true native grades enter success numerators. Missing grades remain "
        "unknown and do not count as success. Native EOS is task success with zero recorded duplicate "
        "executions under the benchmark's domain-specific accounting; it is not a universal exactly-once guarantee.")
    package = arms["conseqax_guard"]
    receipts = package["costs"]["receipt_count"]["observed_total"]
    paragraphs.append(f"The ConseqaX arm emitted {receipts} audited SDK receipts across "
        f"{package['receipt_episodes_with_at_least_one']}/24 planned episodes with at least one receipt "
        f"({package['audited_grade_available']}/24 episodes had complete audited accounting). "
        "The package consumes unchanged current public verification reports; clean first acknowledgments "
        "can therefore require no receipt. The independent auditor recomputes receipt mappings and replays "
        "the original native guard and physical effects, but does not independently re-execute the SDK. "
        "The integration implements the same recovery decisions as the strong native comparator, rather "
        "than a new recovery algorithm or a claim of causal origin.")
    pair = result["matched_contrasts"]["guard__vs__conseqax_guard"]["endpoints"]
    paragraphs.append("For the native-guard versus ConseqaX-guard comparison, "
        f"{pair['EOS']['both_grades_available']}/24 matched worlds had both native grades available. "
        f"Their TS booleans agreed in {pair['TS']['same_boolean_among_both_available']} and EOS booleans "
        f"agreed in {pair['EOS']['same_boolean_among_both_available']} of those worlds; "
        f"{pair['EOS']['at_least_one_grade_unavailable']}/24 worlds had at least one unavailable grade. "
        "These are descriptive paired outcome agreements. Separately generated model trajectories need "
        "not coincide, and this finite matrix supports neither population equivalence nor algorithmic superiority.")
    conditions = []
    for arm, label in zip(ARMS, ARM_LABELS):
        clean = result["strata"]["condition"]["clean"]["arms"][arm]
        fault = result["strata"]["condition"]["assigned_fault"]["arms"][arm]
        conditions.append(f"{label}: clean TS/EOS {clean['endpoints']['TS']['true_audited']}/12 and "
            f"{clean['endpoints']['EOS']['true_audited']}/12, assigned-fault TS/EOS "
            f"{fault['endpoints']['TS']['true_audited']}/12 and {fault['endpoints']['EOS']['true_audited']}/12 "
            f"(grades available {clean['audited_grade_available']}/12 and {fault['audited_grade_available']}/12)")
    paragraphs.append("Assigned-condition results were " + "; ".join(conditions) + ". "
        "Strata use the prospective assignment, irrespective of whether a policy triggered the fault. "
        "Base task parameters match between clean and fault conditions, but native random seeds depend "
        "on mode; these descriptive condition differences do not identify a fault-only causal effect.")
    costs = []
    for arm, label in zip(ARMS, ARM_LABELS):
        row = arms[arm]
        value = row["costs"]
        costs.append(f"{label}: {value['boundary_execute_attempts']['observed_total']} execute attempts, "
            f"{value['public_verify_attempts']['observed_total']} public verification attempts, "
            f"{value['outer_wait_attempts']['observed_total']} explicit wait attempts and "
            f"{value['model_dispatches']['observed_total']} model generation dispatches "
            f"from {row['audited_grade_available']}/24 slots with complete accounting")
    paragraphs.append("Observed work totals were " + "; ".join(costs) + ". "
        "Incomplete slots may have additional unquantified work, so unavailable accounting is not zero. "
        "Boundary attempts are distinct from physical effects; nested clock advances include native tool "
        "latency and are not counted as explicit policy waits. Native virtual time and host wall time are separate costs.")
    usage = []
    for arm, label in zip(ARMS, ARM_LABELS):
        row = arms[arm]["usage"]
        usage.append(f"{label}: {row['input_tokens']['observed_token_total']} known input tokens and "
            f"{row['output_tokens']['observed_token_total']} known output tokens, with "
            f"{row['input_tokens']['unknown_invocations_among_audited_rows']} input-usage and "
            f"{row['output_tokens']['unknown_invocations_among_audited_rows']} output-usage unknown invocations "
            f"among audited rows, plus {row['input_tokens']['rows_without_audited_accounting']} slots "
            "without complete audited accounting")
    paragraphs.append("Saved usage accounting gave " + "; ".join(usage) + ". "
        "Known usage on failed invocations is retained. Cached input is a subset of input tokens and is "
        "not added twice; missing usage is not imputed. Template, domain, fault and paired summaries "
        "are descriptive, without population confidence intervals or significance tests.")
    return paragraphs


def tex_escape(text):
    replacements = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
                    "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}
    return "".join(replacements.get(character, character) for character in text)


def plots(result, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none"})
    output = Path(output)
    filenames = []
    def save(figure, name):
        for extension in ("pdf", "svg", "png"):
            path = output / f"{name}.{extension}"
            figure.savefig(path, bbox_inches="tight", dpi=220)
            filenames.append(path.name)
        plt.close(figure)
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.25), sharey=True, layout="constrained")
    for axis, metric in zip(axes, ("TS", "EOS")):
        values = [result["arms"][arm]["endpoints"][metric] for arm in ARMS]
        true = np.array([row["true_audited"] for row in values])
        false = np.array([row["false_audited"] for row in values])
        missing = np.array([row["grade_unavailable"] for row in values])
        x = np.arange(4)
        axis.bar(x, true, label="Audited true", color="#267c83")
        axis.bar(x, false, bottom=true, label="Audited false", color="#c7d9db")
        axis.bar(x, missing, bottom=true + false, label="Grade unavailable", color="#f5e6b3", hatch="///")
        for index, count in enumerate(true):
            axis.text(index, 24.35, f"{count}/24", ha="center", fontsize=8)
        axis.set(xticks=x, xticklabels=ARM_LABELS, title="Native " + metric, ylim=(0, 27), yticks=(0, 6, 12, 18, 24))
        axis.tick_params(axis="x", rotation=22)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Planned slots per arm")
    axes[1].legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=8)
    save(fig, "limbo-outcomes")
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 5.2), layout="constrained",
                             gridspec_kw={"width_ratios": [1, 1]})
    for axis, axis_name, title in zip(axes, ("template", "mode"), ("Base template (two conditions)", "Assigned fault condition")):
        strata = result["strata"][axis_name]
        names = list(strata)
        values = np.array([[strata[name]["arms"][arm]["endpoints"]["EOS"]["all_planned_success_fraction"]
                            for arm in ARMS] for name in names])
        axis.imshow(values, vmin=0, vmax=1, cmap="YlGnBu", aspect="auto")
        for y, name in enumerate(names):
            for x, arm in enumerate(ARMS):
                row = strata[name]["arms"][arm]
                text = f"{row['endpoints']['EOS']['true_audited']}/{row['planned']}"
                if row["grade_unavailable"]:
                    text += f"\nu{row['grade_unavailable']}"
                axis.text(x, y, text, ha="center", va="center", fontsize=7,
                          color="white" if values[y, x] > 0.6 else "black")
        axis.set(xticks=range(4), xticklabels=ARM_LABELS, yticks=range(len(names)),
                 yticklabels=[name.replace("_", " ") for name in names], title=title)
        axis.tick_params(axis="x", rotation=35)
    fig.suptitle("Native EOS true / all planned slots; u = unavailable grade", fontsize=10)
    save(fig, "limbo-stratification")
    fig, axes = plt.subplots(1, 3, figsize=(9.0, 3.2), layout="constrained")
    for axis, key, title in zip(axes,
        ("boundary_execute_attempts", "public_verify_attempts", "model_dispatches"),
        ("Execute boundary attempts", "Public verification attempts", "Model generation dispatches")):
        entries = [result["arms"][arm]["costs"][key] for arm in ARMS]
        values = [row["observed_total"] for row in entries]
        axis.bar(range(4), values, color=("#9eafb2", "#668f96", "#267c83", "#163f52"))
        ymax = max(values + [1])
        for index, row in enumerate(entries):
            axis.text(index, values[index] + ymax * .025,
                f"{values[index]}" + (f"\nu{row['rows_unavailable']}" if row["rows_unavailable"] else ""),
                ha="center", fontsize=7)
        axis.set(xticks=range(4), xticklabels=ARM_LABELS, title=title, ylim=(0, ymax * 1.3))
        axis.tick_params(axis="x", rotation=35)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Observed totals from audited complete rows")
    fig.suptitle("Missing-row work is unquantified; u = rows without complete accounting", fontsize=9)
    save(fig, "limbo-costs")
    return filenames


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def run(audit_path, protocol_path, commit, output, *, make_figures=True):
    protocol, audit, inputs = validate_inputs(audit_path, protocol_path, commit)
    result = analyze(protocol, audit, inputs)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = output / "inputs"
    sources.mkdir()
    for key, name in (("audit", "audit-result.json"), ("protocol", "protocol.json"),
                      ("audit_manifest", "audit-manifest.json")):
        data = Path(inputs[key]["path"]).read_bytes()
        require({"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                == {field: inputs[key][field] for field in ("sha256", "bytes")},
                "Analysis input changed before provenance copy: " + key)
        (sources / name).write_bytes(data)
    (sources / "analyze_limbo_external_benchmark.py").write_bytes(Path(__file__).read_bytes())
    result["analysis_source"] = binding(Path(__file__))
    result["figures"] = plots(result, output) if make_figures else []
    result["figures_generated"] = make_figures
    write_json(output / "results.json", result)
    (output / "results.md").write_text(markdown(result), encoding="utf-8", newline="\n")
    (output / "results.tex").write_text(latex(result), encoding="utf-8", newline="\n")
    paragraphs = narrative(result)
    (output / "narrative.md").write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8", newline="\n")
    (output / "narrative.tex").write_text("% Generated factual paragraphs; native grades and accounting only.\n"
        + "\n\n".join(tex_escape(paragraph) for paragraph in paragraphs) + "\n", encoding="utf-8", newline="\n")
    manifest = {path.relative_to(output).as_posix(): binding(path)
                for path in output.rglob("*") if path.is_file()}
    write_json(output / "manifest.json", manifest)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--no-figures", action="store_true", help="Explicitly omit figures (for headless validation)")
    args = parser.parse_args()
    result = run(args.audit, args.protocol, args.protocol_commit, args.output,
                 make_figures=not args.no_figures)
    print(json.dumps({"output": str(args.output.resolve()), "planned_slots": result["planned_slots"],
                      "figures": len(result["figures"])}))


if __name__ == "__main__":
    main()
