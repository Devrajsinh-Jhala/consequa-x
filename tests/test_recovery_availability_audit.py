"""Synthetic saved-artifact checks; never runs a world or the case generator."""
from copy import deepcopy
import gzip
import importlib.util
import itertools
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import audit_recovery_availability_sweep as audit

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def original():
    return audit.semantic_auditor(ROOT)


@pytest.fixture(scope="module")
def manual():
    path = Path(__file__).with_name("test_recovery_controller_audit.py")
    spec = importlib.util.spec_from_file_location("availability_synthetic_sqlite_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_protocol():
    cases, schedule = [], []
    for domain, lag, unavailable, incomplete in itertools.product(audit.DOMAINS, *audit.FACTORS.values()):
        index = len(cases)
        name, profile_id = f"synthetic-{index}", f"fixture-{lag}-{unavailable}-{incomplete}"
        payload = {"inventory_reservation": {"warehouse": name, "sku": "fixture", "quantity": 2,
                                              "reservation_ref": name},
                   "support_transition": {"ticket_id": name, "status": "resolved", "queue": "fixture"},
                   "delivery_registration": {"artifact_id": name, "delivery_channel": "fixture",
                                              "checksum": "fixture"}}[domain]
        fields = {"inventory_reservation": ["warehouse", "sku", "reservation_ref"],
                  "support_transition": ["ticket_id"],
                  "delivery_registration": ["artifact_id", "delivery_channel"]}[domain]
        windows = []
        if unavailable:
            windows.append({"start_ms": 0, "until_ms": unavailable, "available": False})
        if incomplete:
            windows.append({"start_ms": 0, "until_ms": incomplete, "complete": False})
        case = {"case_id": name, "family_id": profile_id, "domain": domain,
                "operation_id": f"fixture-operation-{index}", "actor": "fixture-agent", "initial_at_ms": 0,
                "target": {"predicate": "record_present", "expected": payload, "exact_count": 1},
                "payload": payload, "deadline_ms": 100, "stability_ms": 50,
                "recovery_deadline_ms": 250, "safety_horizon_ms": 330, "native_idempotency": True,
                "scope_fields": fields, "scope": {k: payload[k] for k in fields},
                "_availability_profile": {"profile_id": profile_id, "lag_ms": lag,
                                          "unavailable_until_ms": unavailable,
                                          "incomplete_until_ms": incomplete},
                "_world": {"dispatch_plans": [{"status": "success", "response_delay_ms": 2,
                                               "commit_delay_ms": 10}],
                           "readback": {"lag_ms": lag, "windows": windows}}}
        cases.append(case)
        offset = index % 5
        for method in audit.METHODS[offset:] + audit.METHODS[:offset]:
            schedule.append({"trial_id": f"trial_{len(schedule):06d}", "case_id": name,
                             "family_id": profile_id, "domain": domain, "seed": 0, "method": method,
                             **case["_availability_profile"]})
    return {"schema": audit.SCHEMA, "methods": list(audit.METHODS), "case_count": 192,
            "profile_count": 64, "domain_count": 3, "seed_count": 1, "cases": cases, "schedule": schedule,
            "original_study_protocol_sha256": audit.ORIGINAL_PROTOCOL,
            "design": {"factors": deepcopy(audit.FACTORS), "analysis": "fixture finite grid only",
                       "fixed": {"deadline_ms": 100, "stability_ms": 50, "horizon_ms": 150,
                                 "recovery_deadline_ms": 250, "safety_horizon_ms": 330,
                                 "commit_at_ms": 10, "success_response_at_ms": 2,
                                 "native_idempotency": True, "dispatch_cap": 2,
                                 "read_opportunities_ms": [50, 150, 190, 230]}}}


def public_trial(case, times):
    public = {key: case[key] for key in audit.PUBLIC_FIELDS}
    public["registered_at_ms"] = 0
    p = case["_availability_profile"]
    return {"public_case": public, "source_receipt": {"source": "fixture-source"},
            "controller_inputs": {"action_id": case["operation_id"], "actor": case["actor"],
                                  "expected": case["payload"], "scope": case["scope"],
                                  "deadline_ms": 100, "stability_ms": 50, "source": "fixture-source",
                                  "read_times": [50, 150, 190, 230], "max_dispatches": 2,
                                  "exact_count": 1, "scope_fields": case["scope_fields"],
                                  "native_idempotency": True},
            "trajectory": [{"kind": "readback", "at_ms": at,
                            "observation": {"as_of_ms": max(0, at - p["lag_ms"]),
                                            "available": at >= p["unavailable_until_ms"],
                                            "complete": at >= max(p["unavailable_until_ms"],
                                                                  p["incomplete_until_ms"])}}
                           for at in times]}


def test_full_grid_is_valid_without_importing_its_generator():
    assert len(audit.validate_plan(fixture_protocol())) == 192


@pytest.mark.parametrize("mutation,match", [
    (lambda p: p["cases"].pop(), "denominator"),
    (lambda p: p["cases"][0]["_availability_profile"].update(lag_ms=41), "factor"),
    (lambda p: p["cases"][0].update(native_idempotency=False), "capability"),
    (lambda p: p["cases"][0].update(recovery_deadline_ms=251), "temporal"),
    (lambda p: p["cases"][0]["_world"]["dispatch_plans"][0].update(commit_delay_ms=11), "physical"),
    (lambda p: p["cases"][0]["_world"]["readback"].update(windows=[{"available": False}]), "window"),
    (lambda p: p["schedule"][0].update(seed=1), "schedule"),
    (lambda p: p["schedule"][0].update(profile_id="different"), "schedule"),
    (lambda p: p["schedule"].reverse(), "schedule"),
    (lambda p: p["design"]["fixed"].update(read_opportunities_ms=[50, 150, 190, 250]), "fixed"),
])
def test_grid_rejects_undeclared_interventions_or_schedule(mutation, match):
    protocol = fixture_protocol()
    mutation(protocol)
    with pytest.raises(ValueError, match=match):
        audit.validate_plan(protocol)


@pytest.mark.parametrize("lag,unavailable,incomplete,times,known", [
    (0, 0, 0, [150], True), (40, 0, 0, [150], False),
    (40, 170, 170, [150, 190], True), (80, 210, 210, [150, 190, 230], True),
    (95, 0, 0, [150, 190, 230], False), (0, 250, 0, [150, 190, 230], False),
    (0, 0, 250, [150, 190, 230], False),
])
def test_horizon_read_requires_intersection_of_three_conditions(lag, unavailable, incomplete, times, known):
    case = next(c for c in fixture_protocol()["cases"]
                if c["_availability_profile"]["profile_id"] == f"fixture-{lag}-{unavailable}-{incomplete}")
    assert audit.check_public_profile(public_trial(case, times), case) is known


@pytest.mark.parametrize("mutation", [
    lambda r: r["controller_inputs"].update(profile_id="hidden-factor"),
    lambda r: r["public_case"].update(native_idempotency=False),
    lambda r: r["trajectory"][0]["observation"].update(as_of_ms=150),
    lambda r: r["trajectory"][0]["observation"].update(available=False),
    lambda r: r["trajectory"][0].update(at_ms=151),
])
def test_hidden_inputs_or_rewritten_read_semantics_are_rejected(mutation):
    case = fixture_protocol()["cases"][16]
    row = public_trial(case, [150])
    mutation(row)
    with pytest.raises(ValueError):
        audit.check_public_profile(row, case)


@pytest.mark.parametrize("domain", audit.DOMAINS)
def test_pinned_sqlite_auditor_queries_handwritten_fixture(original, manual, tmp_path, domain):
    case = manual.synthetic_case(domain)
    db = manual.raw_database(tmp_path / "fixture.sqlite", case, [manual.effect()])
    assert original.audit_trial(manual.completed_trial(case), db) == manual.completed_metrics()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE effects SET committed_at_ms=11")
    with pytest.raises(ValueError, match="commit time"):
        original.audit_trial(manual.completed_trial(case), db)


def test_coverage_disagreement_is_retained_not_forced_to_prediction():
    protocol = fixture_protocol()
    trials = [{**slot, "status": "failed", "metrics": {"completed": False,
                                                       "operational_safe_recovery": False}}
              for slot in protocol["schedule"]]
    result = audit.observed_analysis(trials, protocol)
    assert result["analytical_expected_true_state_counts"] == {
        "response_retry": 192, "readback_state": 81, "reference": 81,
        "consequax_one_read": 3, "consequax_poll": 81}
    assert result["methods"]["consequax_poll"]["failed"] == 192
    assert result["complete_five_arm_cells"] == 0
    assert all(r["comparable_pairs"] == 0 for r in result["paired_comparisons"])


@pytest.mark.parametrize("value", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_duplicate_or_nonfinite_json_is_rejected(value):
    with pytest.raises(ValueError):
        audit.decode(value)


@pytest.mark.parametrize("name", ["../secret", "/absolute", "D:/absolute", "a\\b", "a//b", "a/./b"])
def test_git_or_artifact_path_traversal_is_rejected(name):
    with pytest.raises(ValueError):
        audit.relative(name)


def test_windows_recorded_claim_path_remains_portable():
    assert audit.recorded_path("D:\\frozen", "output", "claims", "x.json") == "D:\\frozen\\output\\claims\\x.json"


@pytest.fixture
def provenance_fixture(tmp_path, monkeypatch):
    """A synthetic Git-object mapping; deliberately no original host paths exist."""
    root, mapped = tmp_path / "study", tmp_path / "protocol-copy"
    root.mkdir()
    mapped.mkdir()
    protocol = fixture_protocol()
    source_commit, protocol_commit = "1" * 40, "2" * 40
    own = {name: b"synthetic source\n" for name in (
        "scripts/run_recovery_availability_sweep.py", "tests/test_recovery_availability_sweep.py",
        "docs/recovery-availability-sweep.md", "scripts/audit_recovery_availability_sweep.py",
        "tests/test_recovery_availability_audit.py")}
    engine = {name: b"synthetic engine\n" for name in (
        "research/recovery_study/__init__.py", "research/recovery_study/world.py",
        "research/recovery_study/controllers.py", "scripts/run_recovery_controller_study.py")}
    engine[audit.AUDITOR_PATH] = subprocess_blob = audit.git(ROOT, "show", f"{audit.ENGINE_COMMIT}:{audit.AUDITOR_PATH}")
    assert audit.digest(subprocess_blob) == audit.AUDITOR_SHA
    def binding(data):
        return {"sha256": audit.digest(data), "bytes": len(data)}
    protocol.update(source={"root": "D:\\unavailable-frozen-host", "commit": source_commit,
                            "files": {name: binding(data) for name, data in own.items()}},
                    engine={"commit": audit.ENGINE_COMMIT,
                            "files": {name: binding(data) for name, data in engine.items()}},
                    runtime={"framework_version": "2.1.1", "distribution_version": "2.1.1",
                             "python_executable": "D:\\unavailable-python\\python.exe",
                             "python_sha256": "0" * 64, "framework_path": "D:\\unavailable-package",
                             "runtime_file_sha256": {"__init__.py": audit.digest(b"runtime fixture")}},
                    protocol_git_path="output/fixture-protocol/protocol.json")
    case_bytes = audit.encoded({"schema": audit.SCHEMA, "cases": protocol["cases"]})
    protocol["cases_json"] = {**binding(case_bytes), "git_path": "output/fixture-protocol/cases.json"}
    payload = audit.encoded(protocol)
    sha = audit.digest(payload)
    started = {"schema": audit.SCHEMA, "retry_allowed": False, "source_commit": source_commit,
               "original_engine_commit": audit.ENGINE_COMMIT, "protocol_sha256": sha,
               "protocol_commit": protocol_commit, "started_utc": "2026-10-20T00:00:00+00:00",
               "canonical_claim_path": audit.recorded_path(protocol["source"]["root"], "output",
                                                           ".availability-sweep-run-claims", f"{sha}.json"),
               "protocol_path": "E:\\separate-protocol-location\\protocol.json",
               "protocol_git_path": protocol["protocol_git_path"],
               "cases_git_path": protocol["cases_json"]["git_path"],
               "output": "E:\\original-output", "database_root": "F:\\original-databases"}
    for folder in (root, mapped):
        (folder / "protocol.json").write_bytes(payload)
        (folder / "cases.json").write_bytes(case_bytes)
    (root / "started.json").write_bytes(audit.encoded(started))
    (mapped / "run-claim.json").write_bytes(audit.encoded(started))
    blobs = {(source_commit, name): data for name, data in own.items()}
    blobs.update({(audit.ENGINE_COMMIT, name): data for name, data in engine.items()})
    blobs.update({(protocol_commit, protocol["protocol_git_path"]): payload,
                  (protocol_commit, protocol["cases_json"]["git_path"]): case_bytes,
                  (audit.ENGINE_COMMIT, "src/consequa_x/__init__.py"): b"runtime fixture"})
    monkeypatch.setattr(audit, "blob", lambda repo, commit, name: blobs[(commit, name)])
    monkeypatch.setattr(audit, "git", lambda repo, *args: b"src/consequa_x/__init__.py\n"
                        if args[0] == "ls-tree" else b"0\n")
    monkeypatch.setattr(audit.subprocess, "run", lambda *args, **kwargs: None)
    return protocol, started, root, mapped


def test_portable_provenance_does_not_require_or_attest_the_original_host(provenance_fixture):
    protocol, started, root, mapped = provenance_fixture
    result = audit.verify_bindings(protocol, started, root, mapped, ROOT)
    assert result["recorded_host_byte_checks_performed"] is False
    assert result["runtime_files_bound_to_git"] == 1


@pytest.mark.parametrize("change,match", [("claim", "claim"), ("runtime", "runtime"),
                                         ("cases", "case"), ("canonical", "canonical")])
def test_provenance_rejects_changed_copies_or_declarations(provenance_fixture, change, match):
    protocol, started, root, mapped = provenance_fixture
    if change == "claim":
        (mapped / "run-claim.json").write_text("{}")
    elif change == "runtime":
        protocol["runtime"]["runtime_file_sha256"]["__init__.py"] = "f" * 64
    elif change == "cases":
        (mapped / "cases.json").write_text("{}")
    else:
        started["canonical_claim_path"] = "D:\\another-location\\claim.json"
    with pytest.raises(ValueError, match=match):
        audit.verify_bindings(protocol, started, root, mapped, ROOT)


def seal(root):
    names = {p.relative_to(root).as_posix(): audit.digest(p.read_bytes()) for p in root.rglob("*")
             if p.is_file() and p.name not in {"manifest.json", "completion-receipt.json"}}
    (root / "manifest.json").write_bytes(audit.encoded({"schema": audit.SCHEMA, "complete": True, "files": names}))
    receipt = {"schema": audit.SCHEMA, "complete": True, "planned_trials": 960,
               "completed_trials": 0, "failed_trials": 960, "no_retries_or_replacements": True,
               "source_and_runtime_final_recheck": True, "new_model_calls": 0,
               "external_application_calls": 0, "protocol_sha256": audit.digest((root / "protocol.json").read_bytes()),
               "manifest_sha256": audit.digest((root / "manifest.json").read_bytes())}
    (root / "completion-receipt.json").write_bytes(audit.encoded(receipt))


@pytest.fixture
def failed_collection(tmp_path, monkeypatch, original):
    root = tmp_path / "retained-fixtures"
    (root / "trials").mkdir(parents=True)
    protocol, rows = fixture_protocol(), []
    for slot in protocol["schedule"]:
        row = {**slot, "status": "failed", "metrics": {"completed": False, "operational_safe_recovery": False}}
        rows.append(row)
        (root / "trials" / f"{slot['trial_id']}.json.gz").write_bytes(
            gzip.compress(audit.encoded({**row, "schema": audit.SCHEMA}), mtime=0))
    for name, value in (("protocol.json", protocol), ("started.json", {}),
                        ("cases.json", {"schema": audit.SCHEMA, "cases": protocol["cases"]})):
        (root / name).write_bytes(audit.encoded(value))
    summary = original.recompute_summary(rows, protocol)
    summary.update(protocol_sha256=audit.digest((root / "protocol.json").read_bytes()), collection_seconds=0,
                   controlled_profile_count=64, domain_count=3)
    (root / "summary.json").write_bytes(audit.encoded(summary))
    (root / "analysis-rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    seal(root)
    monkeypatch.setattr(audit, "verify_bindings", lambda p, s, r, *args: {
        "protocol_sha256": audit.digest((r / "protocol.json").read_bytes())})
    return root


def test_all_scheduled_failures_stay_operational_zero_semantic_unavailable(failed_collection, tmp_path):
    result = audit.audit_study(failed_collection, tmp_path / "audit", ROOT, tmp_path)
    assert result["passed"] and result["failed_trials"] == 960
    assert result["sqlite_snapshots_queried"] == 0
    summary = audit.decode((tmp_path / "audit" / "recomputed-summary.json").read_bytes())
    assert summary["methods"][0]["metrics"]["safe_recovery"]["observed"] == 0
    assert summary["methods"][0]["metrics"]["operational_safe_recovery"]["sum"] == 0


@pytest.mark.parametrize("tamper,match", [("unexpected", "unexpected|inventory"),
                                         ("raw_identity", "identity"), ("summary", "summary")])
def test_rehashed_artifact_tampering_is_rejected(failed_collection, tmp_path, tamper, match):
    root = failed_collection
    if tamper == "unexpected":
        (root / "unplanned.json").write_text("{}")
    elif tamper == "raw_identity":
        path = root / "trials" / "trial_000000.json.gz"
        row = audit.decode(gzip.decompress(path.read_bytes()))
        row["method"] = "reference"
        path.write_bytes(gzip.compress(audit.encoded(row)))
    else:
        path = root / "summary.json"
        summary = json.loads(path.read_text())
        summary["failed_trials"] = 959
        path.write_bytes(audit.encoded(summary))
    seal(root)
    with pytest.raises(ValueError, match=match):
        audit.audit_study(root, tmp_path / "audit", ROOT, tmp_path)
