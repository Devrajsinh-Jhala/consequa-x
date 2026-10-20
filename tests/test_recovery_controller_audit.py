"""Black-box auditor checks on hand-calculated, synthetic SQLite fixtures.

The AI-assisted author also authored the application world. This is a separate
implementation check, not independent human replication. This test module does
not import the world, controllers, framework, held-out cases or study outputs.
"""

from copy import deepcopy
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess

import pytest

from scripts import audit_recovery_controller_study as auditor
from scripts.audit_recovery_controller_study import AuditError, audit_database, audit_study, audit_trial


def synthetic_case(domain="inventory_reservation"):
    payload = {
        "inventory_reservation": {"warehouse": "audit-store", "sku": "audit-item", "quantity": 2,
                                  "reservation_ref": "audit-reservation"},
        "support_transition": {"ticket_id": "audit-ticket", "status": "resolved", "queue": "audit-queue"},
        "delivery_registration": {"artifact_id": "audit-artifact", "delivery_channel": "audit-channel",
                                   "checksum": "audit-checksum"},
    }[domain]
    fields = {"inventory_reservation": ["warehouse", "sku", "reservation_ref"],
              "support_transition": ["ticket_id"],
              "delivery_registration": ["artifact_id", "delivery_channel"]}[domain]
    return {"case_id": "audit-development", "family_id": "audit-fixtures-only", "domain": domain,
            "operation_id": "dev-op", "actor": "dev-agent", "initial_at_ms": 0,
            "target": {"predicate": "record_present", "expected": deepcopy(payload), "exact_count": 1},
            "payload": deepcopy(payload), "deadline_ms": 50, "stability_ms": 30,
            "recovery_deadline_ms": 120, "safety_horizon_ms": 180,
            "scope_fields": fields, "scope": {name: payload[name] for name in fields},
            "native_idempotency": False}


def effect(effect_id="audit-effect-1", committed=10, removed=None, *, overrides=None,
           action="dev-op", actor="dev-agent", attempt="dev-op:attempt-1", provenance=None):
    return {"effect_id": effect_id, "committed": committed, "removed": removed,
            "overrides": overrides or {}, "action": action, "actor": actor, "attempt": attempt,
            "provenance": ["action_id", "actor", "attempt_id"] if provenance is None else provenance}


def raw_database(path, case, effects=(), pending=()):
    """Construct independent application rows, with no simulator calls."""
    with sqlite3.connect(path) as db:
        db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE effects (
                effect_id TEXT PRIMARY KEY, committed_at_ms INTEGER NOT NULL,
                removed_at_ms INTEGER, payload_json TEXT NOT NULL,
                reported_origin_json TEXT NOT NULL, causal_action_id TEXT,
                causal_actor TEXT NOT NULL, causal_attempt_id TEXT);
            CREATE TABLE pending_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, due_ms INTEGER NOT NULL,
                kind TEXT NOT NULL, event_json TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE idempotency (
                operation_id TEXT PRIMARY KEY, actor TEXT NOT NULL, first_attempt_id TEXT NOT NULL);
            CREATE TABLE inventory_stock (stock_key TEXT PRIMARY KEY, available INTEGER NOT NULL);
            CREATE TABLE inventory_reservations (
                effect_id TEXT PRIMARY KEY REFERENCES effects(effect_id), stock_key TEXT NOT NULL,
                quantity INTEGER NOT NULL, state TEXT NOT NULL);
            CREATE TABLE support_tickets (ticket_id TEXT PRIMARY KEY, status TEXT NOT NULL, queue TEXT NOT NULL);
            CREATE TABLE ticket_transitions (
                effect_id TEXT PRIMARY KEY REFERENCES effects(effect_id), ticket_id TEXT NOT NULL,
                status TEXT NOT NULL, queue TEXT NOT NULL, state TEXT NOT NULL);
            CREATE TABLE delivery_registrations (
                effect_id TEXT PRIMARY KEY REFERENCES effects(effect_id), artifact_id TEXT NOT NULL,
                delivery_channel TEXT NOT NULL, checksum TEXT NOT NULL, state TEXT NOT NULL);
        """)
        active_quantity = 0
        active_tickets = []
        for row in effects:
            payload = dict(case["payload"], **row["overrides"])
            origin = {"action_id": row["action"], "actor": row["actor"], "attempt_id": row["attempt"]}
            reported = {k: value for k, value in origin.items() if k in row["provenance"]}
            db.execute("INSERT INTO effects VALUES(?,?,?,?,?,?,?,?)", (
                row["effect_id"], row["committed"], row["removed"], json.dumps(payload),
                json.dumps(reported), row["action"], row["actor"], row["attempt"]))
            commit = {"effect_id": row["effect_id"], "payload": payload, "origin": origin,
                      "reported_origin": reported, "native": False,
                      "remove_after_ms": row["removed"] - row["committed"] if row["removed"] is not None else None}
            db.execute("INSERT INTO pending_events(due_ms,kind,event_json,applied) VALUES(?,?,?,1)",
                       (row["committed"], "commit", json.dumps(commit)))
            if row["removed"] is not None:
                db.execute("INSERT INTO pending_events(due_ms,kind,event_json,applied) VALUES(?,?,?,1)",
                           (row["removed"], "remove", json.dumps({"effect_id": row["effect_id"]})))
            active = row["removed"] is None
            if case["domain"] == "inventory_reservation":
                stock_key = json.dumps([payload["warehouse"], payload["sku"]], separators=(",", ":"))
                active_quantity += payload["quantity"] if active else 0
                db.execute("INSERT INTO inventory_reservations VALUES(?,?,?,?)", (
                    row["effect_id"], stock_key, payload["quantity"], "active" if active else "released"))
            elif case["domain"] == "support_transition":
                db.execute("INSERT INTO ticket_transitions VALUES(?,?,?,?,?)", (
                    row["effect_id"], payload["ticket_id"], payload["status"], payload["queue"],
                    "active" if active else "reversed"))
                if active:
                    active_tickets.append((row["committed"], payload))
            else:
                db.execute("INSERT INTO delivery_registrations VALUES(?,?,?,?,?)", (
                    row["effect_id"], payload["artifact_id"], payload["delivery_channel"], payload["checksum"],
                    "active" if active else "revoked"))
        if case["domain"] == "inventory_reservation":
            key = json.dumps([case["payload"]["warehouse"], case["payload"]["sku"]], separators=(",", ":"))
            db.execute("INSERT INTO inventory_stock VALUES(?,?)", (key, 20 - active_quantity))
        elif case["domain"] == "support_transition":
            final = max(active_tickets, key=lambda item: item[0])[1] if active_tickets else None
            db.execute("INSERT INTO support_tickets VALUES(?,?,?)", (
                case["payload"]["ticket_id"], final["status"] if final else "open", case["payload"]["queue"]))
        for row in pending:
            event = deepcopy(row["event"])
            if row.get("kind", "commit") == "commit":
                event.setdefault("payload", deepcopy(case["payload"]))
                event.setdefault("reported_origin", deepcopy(event["origin"]))
                event.setdefault("remove_after_ms", None)
                event.setdefault("native", False)
            db.execute("INSERT INTO pending_events(due_ms,kind,event_json,applied) VALUES(?,?,?,?)", (
                row["due_ms"], row.get("kind", "commit"), json.dumps(event), row.get("applied", 0)))
    return path


@pytest.mark.parametrize("domain", ["inventory_reservation", "support_transition", "delivery_registration"])
def test_auditor_recomputes_each_sqlite_domain_without_world_import(tmp_path, domain):
    case = synthetic_case(domain)
    path = raw_database(tmp_path / "single.db", case, [effect()])
    receipt = audit_database(path, case, 180)
    assert receipt["target_satisfied"] is True
    assert receipt["linked_target_satisfied"] is True
    assert receipt["eventual_recovery_satisfied"] is True
    assert receipt["linked_recovery_satisfied"] is True
    assert receipt["target_count"] == 1
    assert receipt["duplicate_count"] == 0
    assert receipt["own_effect_count"] == 1
    assert receipt["metrics"]["committed_effects"] == 1
    assert receipt["metrics"]["removed_effects"] == 0
    assert receipt["records"][0]["_causal_action_id"] == "dev-op"


@pytest.mark.parametrize("domain", ["inventory_reservation", "support_transition", "delivery_registration"])
@pytest.mark.parametrize("removed_at,original_ok", [(80, False), (81, True)])
def test_removal_at_closed_horizon_is_a_real_lifecycle_failure(tmp_path, domain, removed_at, original_ok):
    case = synthetic_case(domain)
    path = raw_database(tmp_path / "boundary.db", case, [effect(committed=50, removed=removed_at)])
    receipt = audit_database(path, case, 180)
    assert receipt["target_satisfied"] is original_ok
    assert receipt["linked_target_satisfied"] is original_ok
    assert receipt["eligible_target_count"] == int(original_ok)
    assert receipt["target_count"] == int(original_ok)
    assert receipt["eventual_recovery_satisfied"] is False
    assert receipt["own_reversed_effect_count"] == 1
    assert receipt["metrics"]["removed_effects"] == 1


def test_transient_extra_match_violates_original_count_even_if_removed_before_final_snapshot(tmp_path):
    case = synthetic_case("support_transition")
    path = raw_database(tmp_path / "transient.db", case, [effect(),
        effect("audit-effect-2", committed=60, removed=70, attempt="dev-op:attempt-2")])
    receipt = audit_database(path, case, 180)
    assert receipt["target_count"] == 1
    assert receipt["eligible_target_count"] == 1
    assert receipt["peak_target_count"] == 2
    assert receipt["target_satisfied"] is False
    assert receipt["eventual_recovery_satisfied"] is True
    assert receipt["recovery_peak_target_count"] == 1
    assert receipt["duplicate_count"] == 1
    assert set(receipt["duplicate_effect_ids"]) == {"audit-effect-1", "audit-effect-2"}
    assert receipt["metrics"]["committed_effects"] == 2
    assert receipt["metrics"]["removed_effects"] == 1


def test_external_matching_state_does_not_establish_own_causality(tmp_path):
    case = synthetic_case("delivery_registration")
    path = raw_database(tmp_path / "external.db", case, [effect(action="curator-op", actor="curator",
                                                               attempt="curator-attempt", provenance=[])])
    receipt = audit_database(path, case, 180)
    assert receipt["target_satisfied"] is True
    assert receipt["eventual_recovery_satisfied"] is True
    assert receipt["linked_target_satisfied"] is False
    assert receipt["linked_recovery_satisfied"] is False
    assert receipt["own_effect_count"] == 0
    assert receipt["linked_target_count"] == 0
    assert receipt["records"][0]["_causal_actor"] == "curator"
    assert "action_id" not in receipt["records"][0]


def test_actual_causality_survives_missing_public_audit_fields(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "missing-origin.db", case, [effect(provenance=[])])
    receipt = audit_database(path, case, 180)
    assert receipt["linked_target_satisfied"] is True
    assert receipt["records"][0]["_causal_actor"] == "dev-agent"
    assert "actor" not in receipt["records"][0]
    assert "action_id" not in receipt["records"][0]


def test_tampered_business_quantity_is_rejected_instead_of_trusting_effect_summary(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "business-tamper.db", case, [effect()])
    with sqlite3.connect(path) as db:
        db.execute("UPDATE inventory_reservations SET quantity=7")
    with pytest.raises(AuditError):
        audit_database(path, case, 180)


def test_wrong_and_late_own_records_are_counted_separately_from_recovery(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "wrong-late.db", case, [
        effect(overrides={"quantity": 3}),
        effect("audit-effect-2", committed=90, attempt="dev-op:attempt-2"),
        effect("audit-effect-3", committed=140, attempt="dev-op:attempt-3"),
    ])
    receipt = audit_database(path, case, 180)
    assert receipt["target_satisfied"] is False
    assert receipt["eligible_target_count"] == 0
    assert receipt["recovery_eligible_target_count"] == 1
    assert receipt["recovery_peak_target_count"] == 2
    assert receipt["eventual_recovery_satisfied"] is False
    assert receipt["own_unwanted_effect_count"] == 2
    assert set(receipt["own_unwanted_effect_ids"]) == {"audit-effect-1", "audit-effect-3"}
    assert receipt["own_effect_count"] == 3 and receipt["duplicate_count"] == 2


def test_original_sla_miss_can_recover_without_rewriting_deadline(tmp_path):
    case = synthetic_case("delivery_registration")
    path = raw_database(tmp_path / "recovered.db", case, [effect(committed=90)])
    receipt = audit_database(path, case, 180)
    assert receipt["target_satisfied"] is False
    assert receipt["linked_target_satisfied"] is False
    assert receipt["eventual_recovery_satisfied"] is True
    assert receipt["linked_recovery_satisfied"] is True
    assert receipt["duplicate_count"] == 0 and receipt["own_unwanted_effect_count"] == 0


def test_pre_horizon_receipt_does_not_claim_future_stability(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "early.db", case, [effect()])
    receipt = audit_database(path, case, 40)
    assert receipt["target_satisfied"] is None
    assert receipt["linked_target_satisfied"] is None
    assert receipt["eventual_recovery_satisfied"] is None
    assert receipt["linked_recovery_satisfied"] is None


def test_future_pending_work_is_not_mislabeled_as_a_committed_effect(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "pending.db", case, pending=[{
        "due_ms": 250, "event": {"effect_id": "future-effect", "origin": {
            "action_id": "dev-op", "actor": "dev-agent", "attempt_id": "dev-op:attempt-1"}}}])
    receipt = audit_database(path, case, 180)
    assert receipt["target_satisfied"] is False
    assert receipt["eventual_recovery_satisfied"] is False
    assert receipt["pending_event_count"] == 1
    assert receipt["own_effect_count"] == 0
    assert receipt["metrics"]["committed_effects"] == 0


def minimal_trial(case, response):
    """Deliberately incomplete scoring fields: boundary rejection must occur first."""
    return {"public_case": case, "trajectory": [
        {"kind": "dispatch", "at_ms": 0, "decision": {"action_id": "dev-op",
         "attempt_id": "dev-op:attempt-1", "idempotency_key": "dev-op"}},
        {"kind": "response", "at_ms": 5, "response": response},
    ], "report": {}, "truth": {}, "metrics": {}}


@pytest.mark.parametrize("work_state", ["pending", "committed"])
def test_terminal_guarantee_contradiction_is_rejected_even_before_commit(tmp_path, work_state):
    case = synthetic_case()
    pending = [{
        "due_ms": 250, "event": {"effect_id": "future-effect", "origin": {
            "action_id": "dev-op", "actor": "dev-agent", "attempt_id": "dev-op:attempt-1"}}}]
    path = raw_database(tmp_path / "terminal-contradiction.db", case,
                        effects=[effect()] if work_state == "committed" else [],
                        pending=pending if work_state == "pending" else [])
    response = {"status": "error", "attempt_id": "dev-op:attempt-1", "response_at_ms": 5,
                "result": {"code": "request_failed"}, "terminal_not_committed": True}
    with pytest.raises(AuditError, match="(?i)terminal|no.commit"):
        audit_trial(minimal_trial(case, response), path)


def test_unallowlisted_case_identity_in_callback_is_rejected(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "hidden-callback.db", case)
    response = {"status": "timeout", "attempt_id": "dev-op:attempt-1", "response_at_ms": 5,
                "result": {"code": "transport_timeout"}, "case_id": "hidden-world-identity"}
    with pytest.raises(AuditError, match="case_id"):
        audit_trial(minimal_trial(case, response), path)


def test_hidden_causal_columns_in_public_observation_are_rejected(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "hidden-observation.db", case)
    trial = {"public_case": case, "trajectory": [{"kind": "readback", "at_ms": 80,
        "observation": {"observation_id": "audit-observation", "source": "sqlite-application-ledger/v1",
                        "observed_at_ms": 80, "as_of_ms": 80, "scope": case["scope"],
                        "complete": True, "available": True,
                        "records": [dict(case["payload"], effect_id="hidden-id", committed_at_ms=10,
                                         _causal_actor="dev-agent")]}}],
        "report": {}, "truth": {}, "metrics": {}}
    with pytest.raises(AuditError, match="_causal"):
        audit_trial(trial, path)


def completed_metrics():
    """Hand-calculated endpoints for one timely own effect and two true claims."""
    return {"completed": True, "operational_safe_recovery": True, "original_completion": True,
            "recovery_completion": True, "safe_recovery": True, "duplicate_event": False,
            "unwanted_event": False, "state_false_success": False, "action_linked_false_success": False,
            "state_wrong_definite": False, "action_linked_wrong_definite": False,
            "state_definite": True, "state_abstention": False, "action_linked_definite": True,
            "action_linked_abstention": False, "dispatches": 1, "reads": 0, "waits": 0,
            "decision_time_ms": 5, "own_effect_count": 1, "duplicate_count": 0, "unwanted_effect_count": 0}


def completed_trial(case):
    """Known single-effect truth, assembled without the auditor or simulator."""
    response = {"status": "success", "attempt_id": "dev-op:attempt-1", "response_at_ms": 5,
                "result": {"code": "accepted"}}
    record = {**case["payload"], "effect_id": "audit-effect-1", "committed_at_ms": 10,
              "action_id": "dev-op", "actor": "dev-agent", "attempt_id": "dev-op:attempt-1",
              "_causal_action_id": "dev-op", "_causal_actor": "dev-agent",
              "_causal_attempt_id": "dev-op:attempt-1"}
    truth = {"at_ms": 180, "horizon_reached": True, "target_satisfied": True, "stable_target": True,
             "eligible_target_count": 1, "peak_target_count": 1, "target_count": 1,
             "linked_target_count": 1, "linked_target_satisfied": True, "sla_duplicate_count": 0,
             "safety_horizon_reached": True, "eventual_recovery_satisfied": True,
             "linked_recovery_satisfied": True, "linked_recovery_target_count": 1,
             "recovery_eligible_target_count": 1, "recovery_peak_target_count": 1,
             "own_unwanted_effect_count": 0, "own_unwanted_effect_ids": [], "own_effect_count": 1,
             "own_reversed_effect_count": 0, "duplicate_count": 0, "duplicate_effect_ids": [],
             "records": [record], "pending_event_count": 0,
             "metrics": {"committed_effects": 1, "removed_effects": 0, "dispatch_calls": 1,
                         "readback_calls": 0, "available_readbacks": 0, "records_returned": 0,
                         "identity_rejections": 0, "native_replays": 0, "new_requests": 1,
                         "business_rejections": 0},
             "dispatch_log": [response], "readback_log": []}
    trial = minimal_trial(case, response)
    trial.update(status="completed", truth=truth, metrics=completed_metrics(), decision_at_ms=5,
                 source_receipt={"source": "synthetic-ledger/v1"},
                 report={"reported_state": True, "reported_action_linked": True,
                         "dispatches": 1, "reads": 0, "waits": 0, "native_idempotency": False})
    return trial


def failed_trial(case):
    return {"status": "failed", "public_case": case, "trajectory": [],
            "source_receipt": {"source": "synthetic-ledger/v1"},
            "metrics": {"completed": False, "operational_safe_recovery": False}}


def test_completed_operational_endpoint_equals_semantic_safe_recovery(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "completed.db", case, [effect()])
    assert auditor.ENDPOINTS[0] == "operational_safe_recovery"
    assert audit_trial(completed_trial(case), path) == completed_metrics()


def test_failed_snapshot_retains_operational_failure_without_semantic_outcomes(tmp_path):
    case = synthetic_case()
    path = raw_database(tmp_path / "failed.db", case, [effect()])
    metrics = audit_trial(failed_trial(case), path)
    assert metrics == {"completed": False, "operational_safe_recovery": False}
    assert "safe_recovery" not in metrics


@pytest.mark.parametrize("metrics", [
    {"completed": False},
    {"completed": False, "operational_safe_recovery": True},
    {"completed": False, "operational_safe_recovery": False, "safe_recovery": False},
    {"completed": False, "operational_safe_recovery": 0},
])
def test_failed_snapshot_rejects_missing_primary_or_invented_semantic_metrics(tmp_path, metrics):
    case = synthetic_case()
    path = raw_database(tmp_path / "failed.db", case)
    trial = failed_trial(case)
    trial["metrics"] = metrics
    with pytest.raises(AuditError, match="operational failure"):
        audit_trial(trial, path)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repository, *arguments, commit_date="2026-10-20T09:00:00+00:00"):
    """Local temporary-fixture Git operations; never touches the study repository."""
    return subprocess.check_output(
        ["git", "-C", str(repository), "-c", "user.name=Synthetic Audit Fixture",
         "-c", "user.email=synthetic-audit@example.invalid", *arguments],
        env={**os.environ, "GIT_AUTHOR_DATE": commit_date, "GIT_COMMITTER_DATE": commit_date},
        stderr=subprocess.PIPE).decode().strip()


def _tiny_summary(protocol):
    """Five one-slot arms: reference failed, the remaining four succeeded."""
    names = tuple(name for name in completed_metrics() if name != "completed")
    endpoints = {}
    groups = []
    for method in protocol["methods"]:
        failed = method == "reference"
        endpoints[method] = {}
        for name in names:
            observed = not failed or name == "operational_safe_recovery"
            value = False if failed else completed_metrics()[name]
            endpoints[method][name] = {"sum": value if observed else 0, "observed": int(observed),
                                      "unavailable": int(not observed), "mean": value if observed else None}
        groups.append({"method": method, "planned": 1, "completed": int(not failed), "failed": int(failed),
                       "metrics": endpoints[method]})
    groups.sort(key=lambda group: group["method"])
    contrasts = []
    for method in protocol["methods"][:-1]:
        metrics = {}
        for name in names:
            observed = method != "reference" or name == "operational_safe_recovery"
            difference = 1 if method == "reference" and name == "operational_safe_recovery" else 0
            metrics[name] = {"pairs": int(observed), "unavailable_pairs": int(not observed),
                             "mean_difference": difference if observed else None,
                             "equal_family_mean_difference": difference if observed else None,
                             "by_family": [{"family_id": "audit-fixtures-only", "pairs": 1,
                                            "sum_difference": difference, "mean_difference": difference}]
                                 if observed else []}
        contrasts.append({"left": "consequax_poll", "right": method, "planned_pairs": 1, "metrics": metrics})
    return {"schema": protocol["schema"], "planned_trials": 5, "completed_trials": 4, "failed_trials": 1,
            "inference_scope": protocol["design"]["analysis"], "methods": groups,
            "families": [dict(group, family_id="audit-fixtures-only") for group in groups],
            "cases": [dict(group, case_id="audit-development") for group in groups],
            "paired_contrasts": contrasts}


def _seal_study(root):
    files = {path.relative_to(root).as_posix(): _digest(path) for path in root.rglob("*")
             if path.is_file() and path.name not in {"manifest.json", "completion-receipt.json"}}
    _write_json(root / "manifest.json", {"complete": True, "files": files})
    _write_json(root / "completion-receipt.json", {
        "complete": True, "manifest_sha256": _digest(root / "manifest.json"),
        "protocol_sha256": _digest(root / "protocol.json"), "no_retries_or_replacements": True,
        "source_and_runtime_final_recheck": True, "new_model_calls": 0, "external_application_calls": 0,
        "planned_trials": 5, "completed_trials": 4, "failed_trials": 1})


@pytest.fixture
def tiny_study(tmp_path, monkeypatch):
    """Exercise the complete auditor on synthetic files and a temporary Git repo.

    Only the production fixed-denominator plan check is replaced for five slots.
    Placeholder source bindings include a synthetic empty case file. No real
    held-out case, runner, controller, world, or framework module is opened/imported.
    """
    source = tmp_path / "synthetic-source"
    source.mkdir()
    names = ["research/recovery_study/controllers.py", "research/recovery_study/world.py",
             "research/recovery_study/heldout_cases.json", "scripts/run_recovery_controller_study.py",
             "scripts/audit_recovery_controller_study.py", "scripts/build_recovery_human_review.py",
             "src/consequa_x/__init__.py"]
    for name in names:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}\n" if name.endswith(".json") else b"# Synthetic placeholder; never imported.\n")
    _git(source, "init")
    _git(source, "add", "--", ".")
    _git(source, "commit", "-m", "Synthetic frozen source", commit_date="2026-10-20T08:00:00+00:00")
    source_commit = _git(source, "rev-parse", "HEAD")
    package = tmp_path / "synthetic-installed-package"
    package.mkdir()
    (package / "__init__.py").write_bytes((source / "src/consequa_x/__init__.py").read_bytes())
    interpreter = tmp_path / "synthetic-interpreter.bin"
    interpreter.write_bytes(b"Synthetic hash fixture only; never executed.\n")
    methods = ["response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll"]
    schedule = [{"trial_id": f"trial_{index:06d}", "case_id": "audit-development",
                 "family_id": "audit-fixtures-only", "domain": "inventory_reservation", "seed": 0,
                 "method": method} for index, method in enumerate(methods)]
    protocol = {"schema": "synthetic-audit-study", "methods": methods, "case_count": 1,
                "family_count": 1, "seed_count": 1, "schedule": schedule,
                "protocol_git_path": "output/synthetic-protocol-2026-10-20/protocol.json",
                "design": {"analysis": "Synthetic fixture only"},
                "source": {"root": str(source), "commit": source_commit,
                           "files": {name: {"sha256": _digest(source / name),
                                             "bytes": (source / name).stat().st_size} for name in names}},
                "runtime": {"framework_version": "2.1.1", "distribution_version": "2.1.1",
                            "python_executable": str(interpreter), "python_sha256": _digest(interpreter),
                            "framework_path": str(package),
                            "runtime_file_sha256": {"__init__.py": _digest(package / "__init__.py")}}}
    _write_json(source / protocol["protocol_git_path"], protocol)
    _git(source, "add", "--", protocol["protocol_git_path"])
    _git(source, "commit", "-m", "Synthetic prospective protocol")
    root = tmp_path / "synthetic-collection"
    root.mkdir()
    _write_json(root / "protocol.json", protocol)
    digest = _digest(root / "protocol.json")
    canonical = source / f"output/.recovery-run-claims/{digest}.json"
    started = {"protocol_sha256": digest, "retry_allowed": False, "started_utc": "2026-10-20T10:00:00+00:00",
               "protocol_commit": _git(source, "rev-parse", "HEAD"), "source_commit": source_commit,
               "canonical_claim_path": str(canonical.resolve()),
               "protocol_path": str((source / protocol["protocol_git_path"]).resolve()),
               "output": str(root.resolve())}
    _write_json(root / "started.json", started)
    _write_json(canonical, started)
    _write_json(source / protocol["protocol_git_path"].rsplit("/", 1)[0] / "run-claim.json", started)
    case = synthetic_case()
    raw_path = raw_database(tmp_path / "known-single-effect.db", case, [effect()])
    compact = []
    for slot in schedule:
        trial = failed_trial(case) if slot["method"] == "reference" else completed_trial(case)
        trial.update(slot)
        if trial["status"] == "completed":
            name = f"databases/{slot['trial_id']}.sqlite.gz"
            packed = root / name
            packed.parent.mkdir(exist_ok=True)
            packed.write_bytes(gzip.compress(raw_path.read_bytes(), mtime=0))
            trial["database"] = {"path": name, "sha256_uncompressed": _digest(raw_path)}
        retained = root / f"trials/{slot['trial_id']}.json.gz"
        retained.parent.mkdir(exist_ok=True)
        retained.write_bytes(gzip.compress(json.dumps(trial, sort_keys=True).encode(), mtime=0))
        compact.append({**slot, "status": trial["status"], "metrics": trial["metrics"]})
    (root / "analysis-rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in compact), encoding="utf-8")
    _write_json(root / "summary.json", {**_tiny_summary(protocol), "collection_seconds": 0.25,
                                       "protocol_sha256": _digest(root / "protocol.json")})
    _seal_study(root)

    def tiny_plan_check(value):
        assert value["schedule"] == schedule
        assert value["methods"] == methods

    monkeypatch.setattr(auditor, "_validate_plan", tiny_plan_check)
    return {"root": root, "output": tmp_path / "synthetic-audit", "source": source, "package": package,
            "interpreter": interpreter, "protocol": protocol, "schedule": schedule}


def test_tiny_full_study_audits_all_retained_bytes_sources_runtime_rows_and_primary_denominators(tiny_study):
    fixture = tiny_study
    result = audit_study(fixture["root"], fixture["output"])
    assert result["passed"] is True
    assert result["sqlite_snapshots_queried"] == 4
    assert result["failed_slots_without_databases"] == ["trial_000002"]
    assert result["source_files_verified"] == 7
    assert result["installed_package_files_verified"] == 1
    assert result["protocol_git_path"] == "output/synthetic-protocol-2026-10-20/protocol.json"
    summary = json.loads((fixture["output"] / "recomputed-summary.json").read_text())
    reference = next(row for row in summary["methods"] if row["method"] == "reference")
    assert reference["metrics"]["operational_safe_recovery"] == {
        "sum": 0, "observed": 1, "unavailable": 0, "mean": 0.0}
    assert reference["metrics"]["safe_recovery"]["observed"] == 0
    contrast = next(row for row in summary["paired_contrasts"] if row["right"] == "reference")
    assert contrast["metrics"]["operational_safe_recovery"]["pairs"] == 1
    assert contrast["metrics"]["operational_safe_recovery"]["mean_difference"] == 1
    assert contrast["metrics"]["safe_recovery"]["unavailable_pairs"] == 1


@pytest.mark.parametrize("tamper,match", [
    ("artifact", "artifact hash mismatch"),
    ("manifest", "manifest hash mismatch"),
    ("unmanifested", "inventory"),
    ("analysis", "analysis row differs"),
    ("trial_metric", "endpoint metric mismatch"),
    ("failed_primary", "operational failure"),
    ("failed_semantic", "operational failure"),
    ("summary", "summary (numeric|value) mismatch"),
    ("lost_database", "lost its SQLite"),
])
def test_full_study_rejects_rehashed_row_summary_and_artifact_tampering(tiny_study, tamper, match):
    fixture, reseal = tiny_study, True
    root = fixture["root"]
    if tamper in {"artifact", "manifest"}:
        path = root / ("summary.json" if tamper == "artifact" else "manifest.json")
        path.write_bytes(path.read_bytes() + b" ")
        reseal = False
    elif tamper == "unmanifested":
        (root / "extra.txt").write_text("unmanifested", encoding="utf-8")
        reseal = False
    elif tamper == "analysis":
        path = root / "analysis-rows.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["metrics"]["operational_safe_recovery"] = False
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    elif tamper in {"trial_metric", "failed_primary", "failed_semantic", "lost_database"}:
        index = 2 if tamper.startswith("failed_") else 0
        path = root / f"trials/trial_{index:06d}.json.gz"
        trial = json.loads(gzip.decompress(path.read_bytes()))
        if tamper == "trial_metric":
            trial["metrics"]["safe_recovery"] = False
        elif tamper == "failed_primary":
            del trial["metrics"]["operational_safe_recovery"]
        elif tamper == "failed_semantic":
            trial["metrics"]["safe_recovery"] = False
        else:
            (root / trial.pop("database")["path"]).unlink()
        path.write_bytes(gzip.compress(json.dumps(trial).encode(), mtime=0))
    elif tamper == "summary":
        path = root / "summary.json"
        summary = json.loads(path.read_text())
        summary["methods"][0]["metrics"]["operational_safe_recovery"]["observed"] = 0
        _write_json(path, summary)
    if reseal:
        _seal_study(root)
    with pytest.raises(AuditError, match=match):
        audit_study(root, fixture["output"])
    assert not fixture["output"].exists()


@pytest.mark.parametrize("tamper,match", [
    ("source", "frozen source file mismatch"),
    ("interpreter", "interpreter executable binding mismatch"),
    ("package", "installed package file changed"),
    ("package_inventory", "package file inventory mismatch"),
])
def test_full_study_independently_detects_source_and_runtime_changes(tiny_study, tamper, match):
    fixture = tiny_study
    if tamper == "source":
        path = fixture["source"] / "scripts/audit_recovery_controller_study.py"
    elif tamper == "interpreter":
        path = fixture["interpreter"]
    elif tamper == "package":
        path = fixture["package"] / "__init__.py"
    else:
        path = fixture["package"] / "unexpected.py"
    path.write_bytes(b"Changed synthetic binding.\n")
    with pytest.raises(AuditError, match=match):
        audit_study(fixture["root"], fixture["output"])


def test_source_worktree_hash_cannot_replace_the_committed_git_blob(tiny_study):
    fixture = tiny_study
    protocol = deepcopy(fixture["protocol"])
    name = "scripts/audit_recovery_controller_study.py"
    path = fixture["source"] / name
    path.write_bytes(b"Changed synthetic source with updated working-file binding.\n")
    protocol["source"]["files"][name] = {"sha256": _digest(path), "bytes": path.stat().st_size}
    with pytest.raises(AuditError, match="committed Git blob"):
        auditor._verify_source_runtime(protocol)


@pytest.mark.parametrize("tamper,match", [
    ("postdated", "postdates collection start"),
    ("naive_start", "lacks a timezone"),
    ("invalid_start", "invalid protocol/start timestamp"),
    ("wrong_blob", "committed protocol blob"),
    ("unrelated_commit", "not an ancestor"),
])
def test_full_study_checks_protocol_commit_blob_ancestry_and_time_independently(tiny_study, tamper, match):
    fixture = tiny_study
    root, source = fixture["root"], fixture["source"]
    started = json.loads((root / "started.json").read_text())
    if tamper == "postdated":
        started["started_utc"] = "2026-10-20T08:59:59+00:00"
    elif tamper == "naive_start":
        started["started_utc"] = "2026-10-20T10:00:00"
    elif tamper == "invalid_start":
        started["started_utc"] = "not-a-timestamp"
    elif tamper == "wrong_blob":
        path = source / fixture["protocol"]["protocol_git_path"]
        path.write_bytes(path.read_bytes() + b" ")
        _git(source, "add", "--", fixture["protocol"]["protocol_git_path"])
        _git(source, "commit", "-m", "Synthetic changed protocol")
        started["protocol_commit"] = _git(source, "rev-parse", "HEAD")
    else:
        _git(source, "checkout", "--orphan", "synthetic-unrelated")
        _git(source, "commit", "-m", "Synthetic unrelated history")
        started["protocol_commit"] = _git(source, "rev-parse", "HEAD")
    _write_json(root / "started.json", started)
    _seal_study(root)
    with pytest.raises(AuditError, match=match):
        audit_study(root, fixture["output"])


def test_protocol_commit_timestamp_equal_to_collection_start_is_admitted(tiny_study):
    fixture = tiny_study
    started = json.loads((fixture["root"] / "started.json").read_text())
    started["started_utc"] = "2026-10-20T09:00:00Z"
    binding = auditor._verify_protocol_commit(fixture["protocol"], started,
                                               _digest(fixture["root"] / "protocol.json"))
    assert binding["protocol_commit"] == started["protocol_commit"]


@pytest.mark.parametrize("tamper,match", [
    ("canonical_path", "canonical run claim path"),
    ("canonical_bytes", "canonical run claim bytes"),
    ("source_commit", "start source commit"),
    ("output_path", "start output path"),
    ("protocol_file", "supplied protocol file"),
    ("local_claim", "protocol-local run claim bytes"),
])
def test_full_study_checks_shared_run_claim_location_and_exact_bytes(tiny_study, tamper, match):
    fixture = tiny_study
    root = fixture["root"]
    path = root / "started.json"
    started = json.loads(path.read_text())
    if tamper == "canonical_path":
        started["canonical_claim_path"] = str((root.parent / "alternate-claim.json").resolve())
    elif tamper == "canonical_bytes":
        canonical = fixture["source"] / f"output/.recovery-run-claims/{started['protocol_sha256']}.json"
        canonical.write_bytes(canonical.read_bytes() + b" ")
    elif tamper == "source_commit":
        started["source_commit"] = "0" * 40
    elif tamper == "output_path":
        started["output"] = str((root.parent / "different-collection").resolve())
    elif tamper == "protocol_file":
        supplied = fixture["source"] / fixture["protocol"]["protocol_git_path"]
        supplied.write_bytes(supplied.read_bytes() + b" ")
    else:
        local_claim = (fixture["source"] / fixture["protocol"]["protocol_git_path"]).parent / "run-claim.json"
        local_claim.write_bytes(local_claim.read_bytes() + b" ")
    _write_json(path, started)
    _seal_study(root)
    with pytest.raises(AuditError, match=match):
        audit_study(root, fixture["output"])


def test_production_plan_validator_checks_full_synthetic_rotation_without_case_content():
    methods = ["response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll"]
    domains = ["inventory_reservation", "support_transition", "delivery_registration"]
    slots = []
    for case in range(24):
        for seed in range(128):
            for arm in range(5):
                slots.append({"trial_id": f"trial_{len(slots):06d}", "case_id": f"synthetic-{case}",
                              "family_id": f"synthetic-family-{case // 2}", "domain": domains[case // 8],
                              "seed": seed, "method": methods[(case + seed + arm) % 5]})
    protocol = {"methods": methods, "case_count": 24, "family_count": 12, "seed_count": 128,
                "schedule": slots}
    auditor._validate_plan(protocol)
    slots[1]["method"] = methods[0]
    with pytest.raises(AuditError, match="duplicate paired"):
        auditor._validate_plan(protocol)
