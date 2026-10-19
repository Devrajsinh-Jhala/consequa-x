"""Audit sealed migration artifacts with standard-library JSON arithmetic only.

Never imports the framework, study runner, collector, or evaluator truth.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


CORE = ("status", "origin", "effect_ids", "attributable_effect_ids")
LEGACY = ("contract_id", "status", "observed_at_ms", "evidence", "origin",
          "effect_ids", "attributable_effect_ids", "reason")
PRIMARY = (
    "migration_success", "structural_legacy_projection_equal", "schema_roundtrip_equal",
    "migration_receipts_preserved", "old_reverify_core_equal", "fresh_core_equal",
    "fresh_state_equal", "fresh_origin_equal", "fresh_action_linked_equal",
    "fresh_receipt_identity_equal", "assessment_status_preserved",
    "migration_alignment_equal", "fresh_alignment_equal",
    "old_recorded_explanation_alignment_equal", "old_analysis_prediction_equal",
)
SECONDARY = ("fresh_full_legacy_receipts_equal", "old_reverify_full_receipts_equal",
             "migration_codes_equal", "fresh_codes_equal")
CHECKS = 0
BOUND_FILES = 0


def need(value, message):
    global CHECKS
    CHECKS += 1
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def projected(obj, keys):
    return {key: obj[key] for key in keys}


def safe(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    need(path != root and root in path.parents, f"Inventory path escapes root: {name}")
    return path


def inventory(root, expected, exact=True):
    global BOUND_FILES
    root = Path(root)
    if exact:
        actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
                  and p.suffix != ".pyc" and "__pycache__" not in p.parts}
        need(actual == set(expected), f"Inventory membership changed: {root}")
    for name, binding in expected.items():
        path = safe(root, name)
        need(path.is_file(), f"Missing bound file: {path}")
        need(path.stat().st_size == binding["bytes"], f"Size changed: {path}")
        need(sha(path) == binding["sha256"], f"Hash changed: {path}")
        BOUND_FILES += 1


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def source(root, pin):
    where = Path(pin["root"])
    need(git(where, "rev-parse", "HEAD").decode().strip() == pin["commit"],
         "Frozen source HEAD moved")
    inventory(where, pin["files"], exact=False)
    for name, binding in pin["files"].items():
        body = git(root, "show", f"{pin['commit']}:{name}")
        need(hashlib.sha256(body).hexdigest() == binding["sha256"],
             f"Pinned disk source differs from committed blob: {name}")


def identifier(value):
    return isinstance(value, str) and bool(value.strip())


def integer(value):
    return type(value) is int


def refund_reference(action, obs):
    """Independent exhaustive-snapshot arithmetic, not a call to either verifier."""
    contract, expected = action["contract"], action["contract"]["expected"]
    horizon = contract["deadline_ms"] + contract.get("stability_ms", 0)
    deadline, registered = contract["deadline_ms"], action["registered_at_ms"]
    unknown = {"status": "unknown", "origin": "unknown", "effect_ids": [],
               "attributable_effect_ids": [], "target_effect_ids": None, "findings": []}
    scope, watermark = obs["scope"], obs["as_of_ms"]
    if (not obs.get("available", True) or not obs.get("complete", True)
            or scope.get("payment_id") != expected["payment_id"]
            or ("currency" in scope and scope["currency"] != expected["currency"])
            or watermark < horizon):
        return unknown
    relevant, seen = [], set()
    for record in obs["records"]:
        fields = {"effect_id", "payment_id", "amount_minor", "currency", "committed_at_ms", "status"}
        if not fields <= record.keys():
            return unknown
        committed, reversal = record["committed_at_ms"], record.get("reversed_at_ms")
        if (not identifier(record["effect_id"]) or record["effect_id"] in seen
                or not integer(committed) or not 0 <= committed <= watermark
                or not integer(record["amount_minor"]) or record["amount_minor"] <= 0
                or not identifier(record["payment_id"]) or not identifier(record["currency"])
                or record["status"] not in ("processed", "reversed")
                or any(key in record and not identifier(record[key])
                       for key in ("actor", "action_id", "attempt_id"))
                or ("reversed_at_ms" in record and (
                    not integer(reversal) or not committed <= reversal <= watermark))
                or (record["status"] == "reversed" and reversal is None)
                or (record["status"] == "processed" and reversal is not None)
                or record["payment_id"] != expected["payment_id"]):
            return unknown
        seen.add(record["effect_id"])
        if registered <= committed <= horizon:
            relevant.append(record)
    payload = [r for r in relevant if r["amount_minor"] == expected["amount_minor"]
               and r["currency"] == expected["currency"]]
    persistent = [r for r in payload if r.get("reversed_at_ms", horizon + 1) > horizon]
    eligible = [r for r in persistent if r["committed_at_ms"] <= deadline]
    points = {deadline, horizon}
    points.update(r["committed_at_ms"] for r in payload if deadline < r["committed_at_ms"] <= horizon)
    points.update(r["reversed_at_ms"] for r in payload if deadline < r.get("reversed_at_ms", horizon + 1) <= horizon)
    # Evaluate at every simultaneous transition, independently of the production delta sweep.
    peak = max(sum(r["committed_at_ms"] <= time < r.get("reversed_at_ms", horizon + 1)
                   for r in payload) for time in points)
    linked = [r for r in relevant if r.get("action_id") == action["action_id"]
              and r.get("actor", action["actor"]) == action["actor"]]
    origin = ("confirmed" if linked else "other_actor" if relevant and all(
        r.get("actor") and r["actor"] != action["actor"]
        and r.get("action_id") != action["action_id"] for r in relevant) else "unknown")
    count = contract.get("exact_count", 1)
    satisfied = bool(eligible) if count is None else len(eligible) == count and peak == count
    findings = []
    def finding(code, records):
        findings.append({"code": code, "effect_ids": [r["effect_id"] for r in records]})
    if count is not None and peak > count:
        finding("EXCESS_EFFECTS", payload)
        if len(linked) > count:
            finding("DUPLICATE_EFFECT", linked)
    mismatched = [r for r in linked if r["amount_minor"] != expected["amount_minor"]
                  or r["currency"] != expected["currency"]]
    if mismatched:
        finding("PARAMETER_MISMATCH", mismatched)
    partial = [r for r in linked if 0 < r["amount_minor"] < expected["amount_minor"]]
    if partial:
        finding("PARTIAL_EFFECT", partial)
    reversed_rows = [r for r in linked if r.get("reversed_at_ms", horizon + 1) <= horizon]
    if reversed_rows:
        finding("REVERSED_EFFECT", reversed_rows)
    targets = [r["effect_id"] for r in linked if r in eligible]
    return {"status": "satisfied" if satisfied else "violated", "origin": origin,
            "effect_ids": [r["effect_id"] for r in relevant],
            "attributable_effect_ids": [r["effect_id"] for r in linked],
            "target_effect_ids": targets, "findings": findings}


def matching(action, receipt):
    if receipt["status"] == "unknown":
        return []
    contract, expected = action["contract"], action["contract"]["expected"]
    horizon = contract["deadline_ms"] + contract.get("stability_ms", 0)
    return [r["effect_id"] for r in receipt["evidence"][-1]["details"]["records"]
            if r.get("effect_id") in receipt["attributable_effect_ids"]
            and all(r.get(k) == value for k, value in expected.items())
            and action["registered_at_ms"] <= r["committed_at_ms"] <= contract["deadline_ms"]
            and r.get("reversed_at_ms", horizon + 1) > horizon]


def linked_outcome(action, receipt, observation):
    if receipt["status"] == "violated":
        return False
    if receipt["status"] == "unknown" or action["contract"].get("exact_count", 1) == 0:
        return None
    # Source/evidence completeness and validity are checked through the independent reference.
    reference = refund_reference(action, observation)
    need(projected(reference, CORE) == projected(receipt, CORE), "Receipt differs from independent snapshot arithmetic")
    count = action["contract"].get("exact_count", 1)
    target_count = len(matching(action, receipt))
    required = 1 if count is None else count
    if receipt["origin"] == "confirmed" and (target_count >= required if count is None else target_count == required):
        return True
    if receipt["origin"] == "other_actor":
        # For a satisfied positive contract, the independently validated snapshot
        # has enough qualifying effects, all with exclusively external provenance.
        return False
    return None


def canonical(action, receipt, observation):
    return {"state": {"satisfied": True, "violated": False, "unknown": None}[receipt["status"]],
            "origin": receipt["origin"], "action_linked": linked_outcome(action, receipt, observation)}


def alignment(status, reported, targets, new):
    if status == "unknown" or reported not in ("success", "failure"):
        return "unassessable"
    if new and targets is None:
        return "unassessable"
    if status == "satisfied" and not targets:
        return "unassessable"
    return "consistent" if (reported == "success") == (status == "satisfied") else "contradicted"


def diagnoses(receipt, reported, response_statuses, targets, domain_codes, new):
    state = receipt["status"]
    align = alignment(state, reported, targets, new)
    codes = []
    if state == "unknown":
        codes.append("UNKNOWN_OUTCOME")
        if reported != "unknown":
            codes.append("UNVERIFIED_ASSESSMENT")
    else:
        if align == "contradicted":
            codes.append("ASSESSMENT_DIVERGENCE")
        if "timeout" in response_statuses and state == "satisfied" and targets:
            codes.append("ACKNOWLEDGEMENT_EFFECT_DIVERGENCE")
        if "success" in response_statuses and state != "satisfied":
            codes.append("RESPONSE_EFFECT_DIVERGENCE")
        if state != "satisfied":
            codes.append("CONSEQUENCE_VIOLATION")
        if new and align == "unassessable":
            codes.append("UNASSESSABLE_ASSESSMENT")
        codes.extend(domain_codes)
        if receipt["origin"] == "other_actor":
            codes.append("EXTERNAL_ACTOR_EFFECT")
        elif receipt["effect_ids"] and receipt["origin"] == "unknown":
            codes.append("UNCONFIRMED_ORIGIN")
    return codes or ["CONSISTENT_OUTCOME"]


def structural(trace):
    return {"schema_version": "0.1", "trace_id": trace["trace_id"],
            "action": {**trace["actions"][0], "trace_id": trace["trace_id"]},
            "events": [{**e, "trace_id": trace["trace_id"]} for e in trace["events"]],
            "responses": [{k: v for k, v in r.items() if k != "action_id"} for r in trace["responses"]],
            "assessment": {k: v for k, v in trace["assessments"][0].items() if k not in ("assessment_id", "action_id")},
            "observations": trace["observations"],
            "verifications": [projected(r, LEGACY) for r in trace["verifications"]]}


def receipt_identity(receipt):
    return {**projected(receipt, ("contract_id", "observed_at_ms", "effect_ids", "attributable_effect_ids")),
            "evidence": [projected(e, ("observation_id", "source", "as_of_ms")) for e in receipt["evidence"]]}


def observation_for(raw, receipt):
    need(len(receipt["evidence"]) == 1, "Receipt has unsupported multiple evidence items")
    evidence = receipt["evidence"][0]
    found = [o for o in raw["observations"] if o["observation_id"] == evidence["observation_id"]]
    need(len(found) == 1, "Receipt observation join is not unique")
    obs = found[0]
    need(obs["source"] == evidence["source"] and obs["as_of_ms"] == evidence["as_of_ms"], "Receipt source/watermark mismatch")
    return obs


def check_episode(row, raw, saved, migrated, historical_prediction):
    metrics = {name: None for name in PRIMARY + SECONDARY}
    old = row.get("old", {})
    action, reported = raw["action"], raw["assessment"]["status"]
    statuses = [r["status"] for r in raw["responses"]]
    refs = [refund_reference(action, observation_for(raw, r)) for r in raw["verifications"]]
    if "recorded_receipts" in old:
        need(old["recorded_receipts"] == raw["verifications"], "Legacy worker changed recorded receipts")
    for receipt, reference in zip(raw["verifications"], refs, strict=True):
        need(projected(receipt, CORE) == projected(reference, CORE), "Recorded receipt differs from public snapshot arithmetic")
    if migrated is not None:
        need(migrated["schema_version"] == "1.0" and migrated["time_base"] == "relative_ms", "Migration schema/time base changed")
        need(len(migrated["actions"]) == len(migrated["assessments"]) == 1, "Migration action/assessment count changed")
        for r in migrated["responses"] + migrated["assessments"] + migrated["verifications"]:
            need(r["action_id"] == action["action_id"], "Migrated action identity changed")
        need(json.loads(json.dumps(migrated, allow_nan=False)) == migrated, "Migrated JSON does not roundtrip")
        metrics.update(migration_success=True, structural_legacy_projection_equal=structural(migrated) == raw,
                       schema_roundtrip_equal=row["metrics"].get("schema_roundtrip_equal"),
                       migration_receipts_preserved=[projected(r, LEGACY) for r in migrated["verifications"]] == raw["verifications"],
                       assessment_status_preserved=migrated["assessments"][0]["status"] == reported)
        need(row["clock_origin_unrecoverable"] is True, "Clock-origin loss hidden")
        reproduced = 0
        for receipt, original, reference in zip(migrated["verifications"], raw["verifications"], refs, strict=True):
            match = projected(original, CORE) == projected(reference, CORE)
            reproduced += match
            need(receipt["target_effect_ids"] == (reference["target_effect_ids"] if match else None), "Migrated target metadata mismatch")
            need([projected(f, ("code", "effect_ids")) for f in receipt["findings"]] == (reference["findings"] if match else []), "Migrated findings mismatch")
        report = row["migration_report"]
        need(report["reproduced"] == reproduced and report["not_reproduced"] == len(refs) - reproduced
             and report["verifications"] == len(refs), "Migration reproduction count changed")
        for name, receipts in (("target_matching", migrated["verifications"]), ("fresh_target_matching", row.get("fresh_receipts", []))):
            if name in row:
                expected = {"unavailable": sum(r["target_effect_ids"] is None for r in receipts),
                            "empty": sum(r["target_effect_ids"] == [] for r in receipts),
                            "nonempty": sum(bool(r["target_effect_ids"]) for r in receipts)}
                need(row[name] == expected, f"Wrong {name} count")
    elif row.get("error_stage") == "migration":
        metrics["migration_success"] = False
    if "fresh_receipts" in old:
        need(len(old["fresh_receipts"]) == len(refs), "Legacy fresh receipt count changed")
        for receipt, reference in zip(old["fresh_receipts"], refs, strict=True):
            need(projected(receipt, CORE) == projected(reference, CORE), "Legacy fresh receipt fails independent arithmetic")
        metrics["old_reverify_core_equal"] = [projected(r, CORE) for r in old["fresh_receipts"]] == [projected(r, CORE) for r in old["recorded_receipts"]]
        metrics["old_reverify_full_receipts_equal"] = old["fresh_receipts"] == old["recorded_receipts"]
    if "fresh_receipts" in row:
        need(len(row["fresh_receipts"]) == len(refs), "Fresh2.0 receipt count changed")
        for receipt, reference, recorded in zip(row["fresh_receipts"], refs, raw["verifications"], strict=True):
            need(receipt["action_id"] == action["action_id"], "Fresh receipt action ID changed")
            need(projected(receipt, CORE) == projected(reference, CORE), "Fresh2.0 receipt fails independent arithmetic")
            need(receipt["target_effect_ids"] == reference["target_effect_ids"], "Fresh target metadata mismatch")
            need([projected(f, ("code", "effect_ids")) for f in receipt["findings"]] == reference["findings"], "Fresh findings mismatch")
            observation_for(raw, receipt)
            need(receipt["contract_id"] == action["contract"]["contract_id"], "Fresh receipt contract changed")
            need(receipt["observed_at_ms"] == observation_for(raw, recorded)["observed_at_ms"], "Fresh receipt time changed")
        latest = row["fresh_receipts"][-1]
        prediction = canonical(action, latest, observation_for(raw, latest))
        need(row["fresh_prediction"] == prediction, "Fresh canonical prediction arithmetic changed")
    for phase, receipts, new in (("recorded", old.get("recorded_receipts"), False),
                                 ("old_fresh", old.get("fresh_receipts"), False),
                                 ("migration", migrated["verifications"] if migrated else None, True),
                                 ("fresh", row.get("fresh_receipts"), True)):
        if receipts is None:
            continue
        last = receipts[-1]
        targets = last.get("target_effect_ids") if new else matching(action, last)
        domain = [f["code"] for f in last.get("findings", [])] if new else [f["code"] for f in refs[-1]["findings"]]
        actual_align = alignment(last["status"], reported, targets, new)
        actual_codes = diagnoses(last, reported, statuses, targets, domain, new)
        container = old if phase in ("recorded", "old_fresh") else row
        prefix = "fresh" if phase == "old_fresh" else phase
        if f"{prefix}_alignment" in container:
            need(container[f"{prefix}_alignment"] == actual_align, f"Wrong {phase} alignment arithmetic")
        if f"{prefix}_codes" in container:
            need(container[f"{prefix}_codes"] == actual_codes, f"Wrong ordered {phase} diagnosis codes")
        if phase in ("recorded", "old_fresh") and f"{prefix}_prediction" in container:
            need(container[f"{prefix}_prediction"] == canonical(action, last, observation_for(raw, last)), "Legacy canonical mapping changed")
    if "fresh_receipts" in old and "fresh_receipts" in row:
        metrics["fresh_core_equal"] = [projected(r, CORE) for r in row["fresh_receipts"]] == [projected(r, CORE) for r in old["fresh_receipts"]]
        metrics["fresh_receipt_identity_equal"] = [receipt_identity(r) for r in row["fresh_receipts"]] == [receipt_identity(r) for r in old["fresh_receipts"]]
        metrics["fresh_full_legacy_receipts_equal"] = [projected(r, LEGACY) for r in row["fresh_receipts"]] == old["fresh_receipts"]
    if "fresh_prediction" in old:
        metrics["old_analysis_prediction_equal"] = old["fresh_prediction"] == historical_prediction
        if "fresh_prediction" in row:
            for target in ("state", "origin", "action_linked"):
                metrics[f"fresh_{target}_equal"] = row["fresh_prediction"][target] == old["fresh_prediction"][target]
    if "recorded_alignment" in old:
        metrics["old_recorded_explanation_alignment_equal"] = old["recorded_alignment"] == saved["assessment_alignment"]
    if "migration_alignment" in row and "recorded_alignment" in old:
        metrics["migration_alignment_equal"] = row["migration_alignment"] == old["recorded_alignment"]
        need(row["alignment_became_unassessable"] == (old["recorded_alignment"] != "unassessable" and row["migration_alignment"] == "unassessable"), "Lost-alignment count changed")
    if "fresh_alignment" in row and "fresh_alignment" in old:
        metrics["fresh_alignment_equal"] = row["fresh_alignment"] == old["fresh_alignment"]
    changes = {}
    for phase, old_name in (("migration", "recorded_codes"), ("fresh", "fresh_codes")):
        if old_name in old and f"{phase}_codes" in row:
            new_codes, old_codes = row[f"{phase}_codes"], old[old_name]
            metrics[f"{phase}_codes_equal"] = new_codes == old_codes
            changes[f"{phase}_added"] = sorted(set(new_codes) - set(old_codes))
            changes[f"{phase}_removed"] = sorted(set(old_codes) - set(new_codes))
    if "code_changes" in row:
        need(row["code_changes"] == changes, "Code addition/removal accounting changed")
    for name, value in row["metrics"].items():
        need(name in metrics and metrics[name] == value, f"Stored metric disagrees with audit: {name}")
    for name, value in metrics.items():
        need(row["metrics"].get(name) == value, f"Available metric omitted/changed: {name}")


def audit(root, run, protocol_dir, protocol_commit):
    root, run, protocol_dir = Path(root), Path(run), Path(protocol_dir)
    completion = load(run / "completion-receipt.json")
    protocol = load(protocol_dir / "protocol.json")
    protocol_sha = sha(protocol_dir / "protocol.json")
    need(completion["protocol_sha256"] == protocol_sha, "Completion protocol hash differs")
    need(sha(run / "protocol.json") == protocol_sha, "Run protocol copy differs")
    need(load(protocol_dir / "protocol.sha256.json")["sha256"] == protocol_sha, "Protocol digest receipt differs")
    need(hashlib.sha256(git(root, "show", f"{protocol_commit}:output/v2-migration-protocol-2026-10-19/protocol.json")).hexdigest() == protocol_sha, "Prospective committed protocol differs")
    claim, started = load(protocol_dir / "run-claim.json"), load(run / "started.json")
    need(claim == started and claim["protocol_sha256"] == protocol_sha and claim["retry_allowed"] is False, "Exclusive claim mismatch")
    committed_time = int(git(root, "show", "-s", "--format=%ct", protocol_commit).decode().strip())
    need(committed_time <= datetime.fromisoformat(started["started_utc"]).timestamp(), "Protocol was committed after measurement started")
    need(completion["historical_inputs_unchanged"] is True and completion["retry_allowed"] is False, "Completion integrity policy changed")
    need(sha(run / "summary.json") == completion["summary_sha256"], "Summary hash differs")
    need(sha(run / "artifacts-inventory.json") == completion["artifacts_inventory_sha256"], "Output inventory hash differs")
    expected_out = load(run / "artifacts-inventory.json")
    inventory(run, expected_out, exact=False)
    actual_out = {p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file()}
    need(actual_out == set(expected_out) | {"artifacts-inventory.json", "completion-receipt.json"}, "Unbound or missing run artifact")
    for arm in ("current", "legacy"):
        source(root, protocol[arm])
    need(subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", protocol["current"]["commit"], protocol_commit], capture_output=True).returncode == 0, "Protocol does not descend from source commit")
    runtime = load(run / "runtime-metadata.json")
    need(runtime == protocol["runtime_metadata"], "Runtime metadata differs from freeze")
    for key, arm, version in (("python", "current", "2.0.0"), ("legacy_python", "legacy", "1.1.0")):
        pin = protocol[key]
        need(sha(pin["executable"]) == pin["sha256"], "Interpreter hash changed")
        actual = json.loads(subprocess.check_output([pin["executable"], "-I", "-B", "-c", "import json,sys;print(json.dumps({'version':sys.version,'executable':sys.executable}))"]))
        need(actual["version"] == pin["version"] and Path(actual["executable"]).resolve() == Path(pin["executable"]).resolve(), "Interpreter identity changed")
        need(runtime[arm]["imported_source_version"] == version and Path(runtime[arm]["imported_module"]).resolve() == Path(protocol[arm]["root"]).resolve() / "src/consequa_x/__init__.py", "Imported source identity changed")
        need(runtime[arm]["ambient_distribution_metadata"]["version"] == version, "Ambient distribution version unexpected")
    study, analysis_dir = Path(protocol["study_root"]), Path(protocol["analysis_root"])
    inventory(study, protocol["study_inventory"])
    inventory(analysis_dir, protocol["analysis_inventory"])
    analysis = load(analysis_dir / "analysis.json")
    original = load(study / "protocol.json")
    schedule = original["schedule"]
    method_rows = [r for r in analysis["rows"] if r["method"] == "consequa_state_origin"]
    predictions = {r["slot"]["slot_id"]: r["prediction"] for r in method_rows}
    inputs = protocol["inputs"]
    ids = [i["slot"]["slot_id"] for i in inputs]
    failed = protocol["failed_slots"]
    need(len(ids) == len(set(ids)) == len(method_rows) == len(predictions) == 503, "Retained input/analysis count differs")
    need(len(failed) == 1 and failed[0]["status"] == "failed", "Historical failure lost")
    failed_id = failed[0]["slot"]["slot_id"]
    need(set(ids) == set(predictions) and set(ids) | {failed_id} == {s["slot_id"] for s in schedule} and len(schedule) == 504, "Planned/retained/failed slot coverage differs")
    need(not (study / "episodes" / failed_id / "trace.json").exists(), "Failed historical trace substituted")
    need(sha(study / failed[0]["receipt"]) == failed[0]["receipt_sha256"], "Failed receipt hash differs")
    for name, digest in original["code_sha256"].items():
        if name.startswith("runtime/"):
            key = "src/consequa_x/" + name.removeprefix("runtime/")
            need(protocol["legacy"]["files"][key]["sha256"] == digest, "Legacy runtime differs from original study")
    row_paths = sorted((run / "episodes").glob("episode_*.json"))
    need({p.stem for p in row_paths} == set(ids), "Missing or duplicate result row")
    rows, added, removed = [], Counter(), Counter()
    for item in inputs:
        slot_id = item["slot"]["slot_id"]
        for field in ("trace", "explanation", "receipt"):
            need(sha(study / item[field]) == item[f"{field}_sha256"], f"Input binding changed: {slot_id}")
        raw, saved = load(study / item["trace"]), load(study / item["explanation"])
        row = load(run / "episodes" / f"{slot_id}.json")
        need(row["slot"] == item["slot"] and row["trace_sha256"] == item["trace_sha256"], "Row identity changed")
        need(row.get("historical_analysis_prediction", predictions[slot_id]) == predictions[slot_id] == item["old_analysis_prediction"], "Historical comparison target changed")
        migrated_path = run / "episodes" / slot_id / "migrated-trace.json"
        migrated = load(migrated_path) if migrated_path.exists() else None
        check_episode(row, raw, saved, migrated, predictions[slot_id])
        rows.append(row)
        added.update(row.get("code_changes", {}).get("fresh_added", []))
        removed.update(row.get("code_changes", {}).get("fresh_removed", []))
    summary = load(run / "summary.json")
    need(summary["retained_traces"] == 503 and summary["planned_slots"] == 504 and summary["historical_failed_slots"] == failed, "Summary denominators changed")
    need(summary["plan"] == protocol["plan"] and summary["protocol_sha256"] == protocol_sha, "Summary plan changed")
    for name in PRIMARY + SECONDARY:
        values = Counter(str(r.get("metrics", {}).get(name)) for r in rows)
        expected = {"equal_or_success": values["True"], "different_or_failed": values["False"], "unavailable": values["None"], "retained_denominator": 503, "success_over_504_planned": values["True"] / 504}
        need(summary["metrics"][name] == expected, f"Wrong metric fractions: {name}")
    errors = sum("error" in r or "error" in r.get("old", {}) for r in rows)
    need(summary["processing_errors"] == errors == completion["processing_errors"], "Wrong processing failure count")
    for target, field in (("migrated", "target_matching"), ("fresh", "fresh_target_matching")):
        counts = {k: sum(r.get(field, {}).get(k, 0) for r in rows) for k in ("unavailable", "empty", "nonempty")}
        need(summary[f"{target}_target_matching_receipts"] == counts and summary[f"{target}_target_matching_receipt_denominator"] == sum(counts.values()), "Wrong receipt target denominator")
    for result_key, report_key in (("migration_receipts_reproduced", "reproduced"), ("migration_receipts_not_reproduced", "not_reproduced")):
        need(summary[result_key] == sum(r.get("migration_report", {}).get(report_key, 0) for r in rows), "Wrong migration reproduction sum")
    need(summary["alignment_became_unassessable"] == sum(r.get("alignment_became_unassessable", False) for r in rows), "Wrong lost alignment sum")
    need(summary["fresh_state_counts"] == dict(Counter(str(r["fresh_prediction"]["state"]) for r in rows if "fresh_prediction" in r)), "Wrong known/unknown state counts")
    need(summary["fresh_state_unavailable"] == sum("fresh_prediction" not in r for r in rows), "Wrong unavailable state count")
    need(summary["fresh_alignment_counts"] == dict(Counter(r.get("fresh_alignment", "processing_unavailable") for r in rows)), "Wrong alignment distribution")
    need(completion["new_model_calls"] == protocol["plan"]["new_model_calls"] == 0, "Unexpected new model calls")
    return {"schema": "consequa-v2-migration-artifact-audit-v1", "audited_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": protocol_sha, "summary_sha256": sha(run / "summary.json"),
            "completion_receipt_sha256": sha(run / "completion-receipt.json"), "checks": CHECKS,
            "bound_file_checks": BOUND_FILES, "retained_traces": len(rows), "historical_failed_slot": failed_id,
            "processing_errors": errors, "metrics": summary["metrics"], "fresh_state_counts": summary["fresh_state_counts"],
            "fresh_alignment_counts": summary["fresh_alignment_counts"], "target_matching": summary["fresh_target_matching_receipts"],
            "fresh_code_additions": dict(added), "fresh_code_removals": dict(removed),
            "model_roundtrip_scope": "Runner model roundtrip assertion is counted from sealed rows; auditor independently parses/roundtrips JSON and checks the structural legacy projection, without executing Trace.from_json.",
            "scope": "Separate standard-library artifact/fraction and public-evidence arithmetic check. No framework/runner imports or execution, model calls, raw-file repairs, or human annotation. It is exposed-data conformance, not held-out accuracy, multi-action or all-feature validation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--run", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--protocol-commit", default="dc14dc1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = args.run or args.root / "output/v2-migration-conformance-2026-10-19"
    protocol = args.protocol or args.root / "output/v2-migration-protocol-2026-10-19"
    result = audit(args.root, run, protocol, args.protocol_commit)
    args.output.mkdir(parents=True, exist_ok=False)
    result["auditor_sha256"] = sha(Path(__file__))
    dump_new(args.output / "audit.json", result)
    with (args.output / "README.md").open("x", encoding="utf-8") as stream:
        stream.write("# Independent offline migration artifact audit\n\n")
        stream.write(f"Audited {result['retained_traces']} retained traces, the original failed slot and every bound input/source/output file. Processing errors: {result['processing_errors']}.\n\n")
        stream.write("Canonical state, origin, action-linked targets, assessment alignment and ordered diagnoses were recomputed from public saved evidence. Migration preservation and fresh verification remain separate. Every metric fraction/denominator and unknown/unavailable count matches the sealed summary.\n\n")
        stream.write(f"Fresh code additions: `{result['fresh_code_additions']}`; removals: `{result['fresh_code_removals']}`.\n\n")
        stream.write(result["model_roundtrip_scope"] + "\n\n" + result["scope"] + "\n")
    print(json.dumps({k: result[k] for k in ("retained_traces", "processing_errors", "checks", "fresh_code_additions")}, indent=2))


if __name__ == "__main__":
    main()
