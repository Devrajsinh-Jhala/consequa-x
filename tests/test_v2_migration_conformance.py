"""Development fixtures only: these tests never open the 503-trace study corpus."""

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from consequa_x import MigrationReport, RecordVerifier, explain, migrate_trace


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "v2_migration_conformance_runner", ROOT / "scripts/run_v2_migration_conformance.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
FIXTURES = ROOT / "tests/fixtures/v0.1"
CASES = (
    ("refund-timeout-after-commit", True, "confirmed", True),
    ("refund-stale-readback", None, "unknown", None),
    ("refund-another-actor", True, "other_actor", False),
)


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def saved_explanation(name):
    path = FIXTURES / f"{name}.explanation.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # Explicit synthetic expectations for examples without a saved explanation.
    codes = {"refund-stale-readback": ["UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT"],
             "refund-another-actor": ["EXTERNAL_ACTOR_EFFECT"]}
    return {"assessment_alignment": "unassessable", "diagnoses": codes[name]}


def baseline(name, state, origin, linked):
    raw, saved = fixture(name), saved_explanation(name)
    prediction = {"state": state, "origin": origin, "action_linked": linked}
    return {"recorded_receipts": raw["verifications"], "fresh_receipts": raw["verifications"],
            "recorded_prediction": prediction, "fresh_prediction": prediction,
            "recorded_alignment": saved["assessment_alignment"],
            "fresh_alignment": saved["assessment_alignment"],
            "recorded_codes": saved["diagnoses"], "fresh_codes": saved["diagnoses"],
            "assessment_status": raw["assessment"]["status"]}


@pytest.mark.parametrize("name,state,origin,linked", CASES)
def test_public_api_conformance_on_disclosed_released_examples(name, state, origin, linked):
    raw, saved = fixture(name), saved_explanation(name)
    before = copy.deepcopy(raw)
    old = baseline(name, state, origin, linked)
    row, migrated = runner.compare_trace(raw, saved, old, old["fresh_prediction"])
    assert raw == before
    assert migrated["schema_version"] == "1.0"
    assert migrated["time_base"] == "relative_ms"
    assert all(row["metrics"][key] is True for key in runner.PLAN["primary_metrics"])
    assert row["fresh_prediction"] == {"state": state, "origin": origin, "action_linked": linked}
    assert row["migration_report"]["reproduced"] == len(raw["verifications"])


def test_migration_preservation_is_distinct_from_fresh_verifier_agreement():
    name = "refund-timeout-after-commit"
    raw = fixture(name)
    raw["verifications"][0]["origin"] = "unknown"
    raw["verifications"][0]["attributable_effect_ids"] = []
    old = baseline(name, True, "confirmed", True)
    old["recorded_receipts"] = raw["verifications"]
    old["recorded_alignment"] = "unassessable"
    old["recorded_codes"] = ["UNCONFIRMED_ORIGIN"]
    saved = {"assessment_alignment": "unassessable"}
    row, migrated = runner.compare_trace(raw, saved, old, old["fresh_prediction"])
    assert row["metrics"]["migration_receipts_preserved"] is True
    assert row["migration_report"]["not_reproduced"] == 1
    assert migrated["verifications"][0]["origin"] == "unknown"
    assert migrated["verifications"][0]["target_effect_ids"] is None
    assert row["target_matching"]["unavailable"] == 1
    assert row["metrics"]["old_reverify_core_equal"] is False
    assert row["metrics"]["fresh_core_equal"] is True


def test_malformed_legacy_input_is_retained_as_a_migration_failure():
    raw = fixture("refund-timeout-after-commit")
    raw["action"]["trace_id"] = "wrong-trace"
    row, migrated = runner.compare_trace(raw, {}, {"error": {"type": "LegacyError"}}, {})
    assert migrated is None
    assert row["error_stage"] == "migration"
    assert row["metrics"] == {"migration_success": False}


def test_later_verification_error_does_not_get_counted_as_migration_failure(monkeypatch):
    import consequa_x
    name = "refund-timeout-after-commit"
    old = baseline(name, True, "confirmed", True)
    monkeypatch.setattr(consequa_x, "verify", lambda *a, **k: (_ for _ in ()).throw(
        ValueError("development verifier failure")))
    row, migrated = runner.compare_trace(fixture(name), saved_explanation(name), old,
                                         old["fresh_prediction"])
    assert migrated["schema_version"] == "1.0"
    assert row["error_stage"] == "fresh_verification"
    assert row["metrics"]["migration_success"] is True
    assert row["metrics"]["migration_receipts_preserved"] is True
    assert row["metrics"]["migration_alignment_equal"] is True
    assert row["metrics"]["fresh_core_equal"] is None


def test_legacy_fresh_error_preserves_available_recorded_alignment_comparison():
    name = "refund-timeout-after-commit"
    old = baseline(name, True, "confirmed", True)
    for key in ("fresh_receipts", "fresh_prediction", "fresh_alignment", "fresh_codes"):
        old.pop(key)
    old["error"] = {"stage": "legacy_fresh_verification", "type": "DevelopmentError"}
    row, migrated = runner.compare_trace(fixture(name), saved_explanation(name), old,
                                         {"state": True, "origin": "confirmed", "action_linked": True})
    assert migrated is not None
    assert row["metrics"]["migration_alignment_equal"] is True
    assert row["metrics"]["fresh_core_equal"] is None
    assert row["metrics"]["fresh_alignment_equal"] is None
    assert runner.summarize([row], [])["processing_errors"] == 1


def test_semantic_agreement_does_not_normalize_away_diagnosis_changes():
    name = "refund-timeout-after-commit"
    raw, old = fixture(name), baseline(name, True, "confirmed", True)
    raw["assessment"]["status"] = "unknown"
    # Keep the captured assessment event consistent with the synthetic report.
    for event in raw["events"]:
        if event["type"] == "agent_assessment":
            event["data"]["status"] = "unknown"
    old.update(recorded_alignment="unassessable", fresh_alignment="unassessable",
               recorded_codes=["ACKNOWLEDGEMENT_EFFECT_DIVERGENCE"],
               fresh_codes=["ACKNOWLEDGEMENT_EFFECT_DIVERGENCE"])
    row, _ = runner.compare_trace(raw, {"assessment_alignment": "unassessable"},
                                 old, old["fresh_prediction"])
    assert row["metrics"]["fresh_alignment_equal"] is True
    assert row["metrics"]["fresh_codes_equal"] is False
    assert row["code_changes"]["fresh_added"] == ["UNASSESSABLE_ASSESSMENT"]


def test_target_matching_unavailable_is_separate_from_an_empty_match():
    raw = fixture("record-timeout-after-commit")
    report = MigrationReport()
    plain = migrate_trace(raw, report=report)
    assert plain.verifications[0].target_effect_ids is None
    assert report["not_reproduced"] == 1
    assert explain(plain).single_action.assessment_alignment == "unassessable"
    restored = migrate_trace(raw, verifiers={"record_present": RecordVerifier(scope_fields=("order_id",))})
    assert restored.verifications[0].target_effect_ids
    assert explain(restored).single_action.assessment_alignment == "contradicted"


def test_observation_binding_uses_recorded_identity_and_never_the_latest_readback():
    from dataclasses import replace
    trace = migrate_trace(fixture("refund-timeout-after-commit"))
    first = trace.observations[0]
    newer = replace(first, observation_id="unrelated-newer-observation")
    changed = replace(trace, observations=(first, newer))
    assert runner.binding(changed, changed.verifications[0]) is first
    with pytest.raises(ValueError, match="does not identify one"):
        runner.binding(SimpleNamespace(observations=(newer,)), trace.verifications[0])


def test_receipt_identity_and_full_evidence_are_separate_invariants():
    raw = fixture("refund-timeout-after-commit")["verifications"][0]
    changed = copy.deepcopy(raw)
    changed["reason"] = "A changed display reason"
    changed["evidence"][0]["details"]["development_marker"] = True
    assert runner.core(raw) == runner.core(changed)
    assert runner.receipt_identity(raw) == runner.receipt_identity(changed)
    assert runner.legacy_projection(raw) != runner.legacy_projection(changed)
    changed["evidence"][0]["observation_id"] = "other"
    assert runner.receipt_identity(raw) != runner.receipt_identity(changed)


def test_inventory_rejects_tampering_and_additional_files(tmp_path):
    target = tmp_path / "input.json"
    target.write_text("{}", encoding="utf-8")
    frozen = runner.inventory(tmp_path)
    runner.check_inventory(tmp_path, frozen)
    target.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="inventory changed"):
        runner.check_inventory(tmp_path, frozen)
    target.write_text("{}", encoding="utf-8")
    (tmp_path / "replacement.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory changed"):
        runner.check_inventory(tmp_path, frozen)


def test_source_freeze_cannot_hide_a_deleted_tracked_runtime_module(tmp_path, monkeypatch):
    package = tmp_path / "src/consequa_x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="1.1.0"\n', encoding="utf-8")
    def fake_git(root, *args):
        if args[:2] == ("rev-parse", "HEAD"):
            return "a" * 40
        if args[0] == "status":
            assert "src/consequa_x" in args
            return " D src/consequa_x/deleted_module.py"
        pytest.fail("Deleted runtime path was not rejected before inventory pinning")
    monkeypatch.setattr(runner, "git", fake_git)
    with pytest.raises(ValueError, match="deleted_module"):
        runner.source_pin(tmp_path, "a" * 40, research=False)


def test_exclusive_artifacts_preserve_an_interrupted_claim(tmp_path):
    claim = tmp_path / "run-claim.json"
    runner.write_json(claim, {"output_dir": "first", "retry_allowed": False})
    before = claim.read_bytes()
    with pytest.raises(FileExistsError):
        runner.write_json(claim, {"output_dir": "second"})
    assert claim.read_bytes() == before


def slot_fixture():
    schedule = [{"slot_id": f"episode_{index:05d}"} for index in range(504)]
    episodes = [{"slot": slot, "status": "completed" if index != 109 else "failed"}
                for index, slot in enumerate(schedule)]
    predictions = [{"slot": item["slot"], "prediction": {"state": None}}
                   for item in episodes if item["status"] == "completed"]
    return copy.deepcopy(schedule), copy.deepcopy(episodes), copy.deepcopy(predictions)


def test_slot_identity_guard_accepts_exact_development_schedule_coverage():
    schedule, episodes, predictions = slot_fixture()
    episode_index, prediction_index = runner.slot_indices(schedule, episodes, predictions)
    assert len(episode_index) == 504
    assert len(prediction_index) == 503
    assert "episode_00109" not in prediction_index


@pytest.mark.parametrize("mutation", ["duplicate_schedule", "duplicate_episode",
                                      "extra_episode_duplicate", "missing_episode_identity",
                                      "duplicate_prediction", "extra_prediction_duplicate",
                                      "failed_slot_prediction", "missing_prediction"])
def test_slot_identity_guard_rejects_duplicates_and_missing_coverage(mutation):
    schedule, episodes, predictions = slot_fixture()
    if mutation == "duplicate_schedule":
        schedule[-1] = copy.deepcopy(schedule[0])
    elif mutation == "duplicate_episode":
        episodes[-1] = copy.deepcopy(episodes[0])
    elif mutation == "extra_episode_duplicate":
        episodes.append(copy.deepcopy(episodes[0]))
    elif mutation == "missing_episode_identity":
        episodes[-1]["slot"]["slot_id"] = "episode_99999"
    elif mutation == "duplicate_prediction":
        predictions[-1] = copy.deepcopy(predictions[0])
    elif mutation == "extra_prediction_duplicate":
        predictions.append(copy.deepcopy(predictions[0]))
    elif mutation == "failed_slot_prediction":
        predictions[-1]["slot"]["slot_id"] = "episode_00109"
    else:
        predictions.pop()
    with pytest.raises(ValueError, match="unique"):
        runner.slot_indices(schedule, episodes, predictions)


def test_denominators_retain_errors_failed_slot_and_unknown_agreement():
    rows = [{"metrics": {"fresh_state_equal": True}, "fresh_prediction": {"state": None}},
            {"error": {"type": "ValidationError"}, "metrics": {"migration_success": False}}]
    result = runner.summarize(rows, [{"slot": {"slot_id": "historical_failed"}}])
    metric = result["metrics"]["fresh_state_equal"]
    assert metric == {"equal_or_success": 1, "different_or_failed": 0, "unavailable": 1,
                      "retained_denominator": 2, "success_over_504_planned": 1 / 504}
    assert result["processing_errors"] == 1
    assert result["fresh_state_counts"] == {"None": 1}
    assert result["fresh_state_unavailable"] == 1
    assert len(result["historical_failed_slots"]) == 1


def test_protocol_hash_gate_precedes_all_runtime_or_corpus_execution(tmp_path, monkeypatch):
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runner, "get_legacy", lambda *a, **k: pytest.fail("worker executed"))
    with pytest.raises(ValueError, match="Protocol hash differs"):
        runner.run(argparse.Namespace(protocol=protocol, expected_protocol_sha256="0" * 64,
                                      output_dir=tmp_path / "run"))
    assert not (tmp_path / "run-claim.json").exists()


def test_freeze_inventories_without_comparing_any_trace(tmp_path, monkeypatch):
    study, analysis = tmp_path / "study", tmp_path / "analysis"
    study.mkdir()
    analysis.mkdir()
    monkeypatch.setattr(runner, "source_pin", lambda *a, **k: {"files": {}})
    monkeypatch.setattr(runner, "historical_inputs", lambda *a: (
        [{"slot": {"slot_id": "development-only"}}], [{"status": "failed"}], {"code_sha256": {}}))
    monkeypatch.setattr(runner, "python_pin", lambda *a: {"executable": sys.executable})
    monkeypatch.setattr(runner, "source_runtime_pin", lambda *a: {"development_metadata": True})
    monkeypatch.setattr(runner, "compare_trace", lambda *a, **k: pytest.fail("measured logic executed"))
    monkeypatch.setattr(runner, "get_legacy", lambda *a, **k: pytest.fail("worker executed"))
    result = runner.freeze(argparse.Namespace(
        study_dir=study, analysis_dir=analysis, legacy_root=tmp_path,
        expected_current_commit="a" * 40, expected_legacy_commit="b" * 40,
        legacy_python=Path(sys.executable), output_dir=tmp_path / "frozen"))
    assert result["measured_run_executed"] is False
    frozen = runner.read_json(Path(result["protocol"]))
    assert frozen["plan"] == runner.PLAN
    assert result["sha256"] == runner.digest(Path(result["protocol"]))


@pytest.mark.skipif(not os.environ.get("CONSEQUA_V2_LEGACY_ROOT"),
                    reason="Set CONSEQUA_V2_LEGACY_ROOT for the disclosed frozen-1.1 fixture check")
def test_isolated_frozen_1_1_worker_against_three_released_refund_fixtures():
    source = Path(os.environ["CONSEQUA_V2_LEGACY_ROOT"])
    executable = Path(os.environ.get("CONSEQUA_V2_LEGACY_PYTHON", sys.executable))
    items = [{"slot_id": name, "path": str(FIXTURES / f"{name}.json")}
             for name, *_ in CASES]
    result = runner.get_legacy(source, items, python=executable)
    assert result["runtime"]["imported_source_version"] == "1.1.0"
    for name, state, origin, linked in CASES:
        old = result["results"][name]
        assert "error" not in old
        row, _ = runner.compare_trace(fixture(name), saved_explanation(name), old,
                                      {"state": state, "origin": origin, "action_linked": linked})
        assert all(row["metrics"][key] is True for key in runner.PLAN["primary_metrics"])
