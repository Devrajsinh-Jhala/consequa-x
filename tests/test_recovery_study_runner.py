"""Runner development fixtures only; never load the authored held-out corpus."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("recovery_runner", ROOT / "scripts/run_recovery_controller_study.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def case(**world):
    expected = {"artifact_id": "development-item", "delivery_channel": "development-channel",
                "checksum": "development-digest"}
    return {"case_id": "development-only", "family_id": "development-only", "domain": "delivery_registration",
        "operation_id": "development-operation", "actor": "development-agent", "initial_at_ms": 0,
        "target": {"predicate": "record_present", "expected": expected, "exact_count": 1},
        "payload": deepcopy(expected), "deadline_ms": 50, "stability_ms": 30,
        "recovery_deadline_ms": 120, "safety_horizon_ms": 180,
        "scope_fields": ["artifact_id", "delivery_channel"],
        "scope": {"artifact_id": expected["artifact_id"], "delivery_channel": expected["delivery_channel"]},
        "native_idempotency": False, "_world": world}


@pytest.mark.parametrize("method", runner.METHODS)
def test_real_development_world_loop_preserves_budget_and_hidden_boundary(tmp_path, method):
    result = runner.execute(case(), 19, method, tmp_path / "app.sqlite")
    assert result["status"] == "completed", result
    assert result["truth"]["target_satisfied"] is True
    assert result["metrics"]["safe_recovery"] is True
    assert result["report"]["dispatches"] == 1
    assert result["report"]["reads"] <= 4
    assert not {"_world", "case_id", "family_id", "truth", "domain", "seed"} & result["controller_inputs"].keys()
    assert result["controller_inputs"]["max_dispatches"] == 2
    assert result["public_case"]["registered_at_ms"] == 0
    assert result["truth"]["safety_horizon_reached"] is True


def test_timeout_retry_causes_real_extra_effect_but_safe_reference_observes(tmp_path):
    fixture = case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": 2},
                                 {"status": "success", "commit_delay_ms": 2}])
    unsafe = runner.execute(fixture, 19, "response_retry", tmp_path / "retry.sqlite")
    safe = runner.execute(fixture, 19, "reference", tmp_path / "reference.sqlite")
    assert unsafe["status"] == safe["status"] == "completed"
    assert unsafe["metrics"]["duplicate_event"] is True
    assert unsafe["metrics"]["state_false_success"] is True
    assert safe["metrics"]["safe_recovery"] is True
    assert safe["metrics"]["duplicate_event"] is False


def test_known_provider_idempotency_is_equal_public_information(tmp_path):
    fixture = case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": 2}])
    fixture["native_idempotency"] = True
    for method in runner.METHODS:
        row = runner.execute(fixture, 11, method, tmp_path / f"{method}.sqlite")
        assert row["status"] == "completed", row
        assert row["controller_inputs"]["native_idempotency"] is True
        assert row["truth"]["own_effect_count"] == 1
        assert row["truth"]["metrics"]["native_replays"] <= 1


def test_public_terminal_guarantee_allows_safe_productive_retry_before_sla(tmp_path):
    fixture = case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": None, "terminal_not_committed": True},
                                 {"status": "success", "commit_delay_ms": 2}])
    for method in ("reference", "consequax_one_read", "consequax_poll"):
        row = runner.execute(fixture, 3, method, tmp_path / f"{method}.sqlite")
        assert row["status"] == "completed", row
        assert row["metrics"]["original_completion"] is True
        assert row["metrics"]["safe_recovery"] is True
        assert row["metrics"]["dispatches"] == 2


def test_late_recovery_never_relabels_original_deadline(tmp_path):
    row = runner.execute(case(dispatch_plans=[{"status": "timeout", "commit_delay_ms": 100}]),
                         1, "consequax_poll", tmp_path / "late.sqlite")
    assert row["status"] == "completed", row
    assert row["metrics"]["original_completion"] is False
    assert row["metrics"]["recovery_completion"] is True
    assert row["metrics"]["dispatches"] == 1
    assert row["report"]["reported_state"] is False


def test_exhausted_unknown_readbacks_remain_abstentions(tmp_path):
    row = runner.execute(case(readback={"available": False}), 3, "consequax_poll", tmp_path / "unknown.sqlite")
    assert row["status"] == "completed", row
    assert row["report"]["reported_state"] is None
    assert row["metrics"]["state_abstention"] is True
    assert row["metrics"]["reads"] == 4


def test_controller_failure_is_retained_with_truth_and_no_replacement(tmp_path, monkeypatch):
    import research.recovery_study.controllers as controllers
    def fail(*args, **kwargs):
        raise RuntimeError("development injected callback failure")
    monkeypatch.setattr(controllers.Controller, "on_response", fail)
    row = runner.execute(case(), 7, "reference", tmp_path / "failure.sqlite")
    assert row["status"] == "failed"
    assert row["metrics"] == {"completed": False, "operational_safe_recovery": False}
    assert row["error_type"] == "RuntimeError"
    assert row["truth"]["metrics"]["dispatch_calls"] == 1


def test_aggregate_retains_unknown_measurements_and_failed_planned_slots():
    rows = [{"status": "completed", "metrics": {"safe_recovery": True, "operational_safe_recovery": True}},
            {"status": "failed", "metrics": {"completed": False, "operational_safe_recovery": False}}]
    result = runner.aggregate(rows)
    assert result["planned"] == 2 and result["completed"] == result["failed"] == 1
    assert result["metrics"]["safe_recovery"] == {"sum": 1, "observed": 1, "unavailable": 1, "mean": 1.0}
    assert result["metrics"]["operational_safe_recovery"] == {
        "sum": 1, "observed": 2, "unavailable": 0, "mean": 0.5}


def test_summarize_uses_paired_case_seed_and_equal_family_mean():
    rows = []
    for i, family in enumerate(("dev-a", "dev-b")):
        for method in runner.METHODS:
            rows.append({"trial_id": f"development-{len(rows)}", "case_id": f"development-{i}",
                "family_id": family, "domain": "delivery_registration", "seed": 0, "method": method,
                "status": "completed", "metrics": {"safe_recovery": method == "consequax_poll"}})
    protocol = {"schedule": rows, "design": {"analysis": "synthetic development only"}}
    summary = runner.summarize(rows, protocol)
    assert summary["planned_trials"] == summary["completed_trials"] == 10
    for contrast in summary["paired_contrasts"]:
        estimate = contrast["metrics"]["safe_recovery"]
        assert estimate["pairs"] == 2 and estimate["unavailable_pairs"] == 0
        assert estimate["equal_family_mean_difference"] == 1.0


def test_rotation_is_balanced_and_does_not_redraw_cases():
    cases = [{"case_id": f"development-{n}", "family_id": "development-family", "domain": "delivery_registration"}
             for n in range(3)]
    schedule = runner.schedule(cases, 5)
    assert len(schedule) == 75 and len({r["trial_id"] for r in schedule}) == 75
    for n in range(0, len(schedule), 5):
        assert {r["method"] for r in schedule[n:n+5]} == set(runner.METHODS)
        assert len({(r["case_id"], r["seed"]) for r in schedule[n:n+5]}) == 1


def test_case_and_polling_horizons_are_predeclared_and_validated():
    fixture = case()
    runner.validate_case(fixture)
    assert runner.read_schedule(fixture) == [25, 80, 120, 160]
    fixture["safety_horizon_ms"] = 120
    with pytest.raises(ValueError, match="horizon"):
        runner.validate_case(fixture)


def test_writable_checkout_cannot_validate_another_frozen_root(tmp_path):
    with pytest.raises(ValueError, match="Executing checkout"):
        runner.verify_frozen({"source": {"root": str(tmp_path)}})


def test_failed_primary_pairs_remain_in_equal_family_operational_contrast():
    rows = []
    for family in ("development-a", "development-b"):
        for method in runner.METHODS:
            failed = family == "development-b" and method == "consequax_poll"
            rows.append({"case_id": family, "family_id": family, "seed": 0, "method": method,
                "status": "failed" if failed else "completed",
                "metrics": {"completed": not failed, "operational_safe_recovery": not failed}})
    result = runner.summarize(rows, {"schedule": rows, "design": {"analysis": "development only"}})
    comparison = result["paired_contrasts"][0]["metrics"]["operational_safe_recovery"]
    assert comparison["pairs"] == 2 and comparison["unavailable_pairs"] == 0
    assert comparison["equal_family_mean_difference"] == -0.5


def test_copying_protocol_cannot_bypass_the_canonical_exclusive_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "frozen-source")
    protocol = {"source": {"commit": "development-only"}}
    first = runner.reserve_run(tmp_path / "original/protocol.json", protocol, "a" * 64,
                               tmp_path / "output1", "development-protocol-commit")
    assert Path(first["canonical_claim_path"]).is_file()
    with pytest.raises(FileExistsError):
        runner.reserve_run(tmp_path / "copied/protocol.json", protocol, "a" * 64,
                           tmp_path / "output2", "development-protocol-commit")
