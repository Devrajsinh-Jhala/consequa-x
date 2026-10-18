"""Pinned native-estimator integration, evidence parity and fail-closed controls."""

from copy import deepcopy
from dataclasses import replace
import gzip
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


def _module():
    name = "run_upstream_car_study"
    if name not in sys.modules:
        path = Path(__file__).resolve().parents[1] / "scripts/run_upstream_car_study.py"
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@pytest.fixture(scope="module")
def study():
    return _module()


@pytest.fixture(scope="module")
def car(study):
    source = os.environ.get("CONSEQUAX_CAR_SOURCE")
    if not source:
        pytest.skip("Set CONSEQUAX_CAR_SOURCE to the reviewed pinned CAR checkout for integration")
    return study.load_car(source)


def _small(study, mechanism="refund-p50-q50", **changes):
    return study.StudyPlan(repeats=1, samples=2, pairs=2, endpoint_samples=2, seed=80_000_000,
                           mechanisms=(mechanism,), **changes)


def test_default_plan_reserves_nonoverlapping_pairs_and_factual_keys(study):
    plan = study.StudyPlan()
    schedule = study.trial_schedule(plan)
    assert len(schedule) == 1024
    assert plan.shapley_branches == 288
    for trial in schedule:
        slots = study.slots_for(plan, trial)
        assert [item["index"] for item in slots] == list(range(len(slots)))
        assert len({item["continuation_seed"] for item in slots}) == len(slots)
        assert trial["factual_seed"] < slots[0]["continuation_seed"]
    for left, right in zip(schedule, schedule[1:]):
        assert study.slots_for(plan, left)[-1]["continuation_seed"] < right["factual_seed"]


@pytest.mark.parametrize("changes", [
    {"repeats": True}, {"repeats": 0}, {"samples": 1}, {"pairs": 1},
    {"endpoint_samples": 1}, {"seed": -1}, {"seed": 2**31}, {"max_calls": 2},
    {"workers": 0}, {"workers": True}, {"workers": 9},
    {"confidence": True}, {"confidence": float("nan")}, {"confidence": 1.},
    {"mechanisms": ()}, {"mechanisms": ("missing",)},
    {"mechanisms": ["refund-p50-q50"]}, {"mechanisms": ("refund-p50-q50", "refund-p50-q50")},
])
def test_invalid_plans_refuse_before_collection(study, changes):
    with pytest.raises(ValueError):
        study.StudyPlan(**changes)


def test_independent_reference_recovers_physical_interaction_and_dummy(study):
    reference = study.exact_reference("refund-p50-q50")
    assert reference["coalition_bad_rates"] == [.75, .5, 1., 1., .75, .5, 1., 1.]
    assert reference["contrastive"] == [-.25, -.5, 0.]
    assert reference["shapley"] == pytest.approx([-.125, .375, 0.])
    assert reference["endpoint_difference"] == .25
    assert reference["latest_population_rescue"] == 1


def test_reference_idempotency_and_zero_controls(study):
    idempotent = study.exact_reference("idempotent-p50-q50")
    assert idempotent["contrastive"] == [.5, 0., 0.]
    assert idempotent["shapley"] == pytest.approx([-.5, 0., 0.])
    zero = study.exact_reference("refund-p100-q100")
    assert zero["contrastive"] == [0., 0., 0.]
    assert zero["shapley"] == [0., 0., 0.]


def test_reference_never_conditions_on_known_missing_provenance(study):
    reference = study.exact_reference("unknown-provenance-p50-q50")
    assert reference["shapley"] is None
    assert reference["coalition_bad_rates"][0] is None
    assert reference["unknown_probabilities"][0] == .25
    lag = study.exact_reference("lagged-readback-p50-q50")
    assert lag["contrastive"] == [None, None, None]


def test_primary_gate_never_converts_unknown_or_partial_into_numeric_success(study):
    for status in ("unknown", "invalid", "failed", "unstarted"):
        gate = study.primary_gate([{"status": "known"}, {"status": status}], 1)
        assert gate["eligible"] is False
    assert study.primary_gate([{"status": "known"}], None)["eligible"] is False
    assert study.primary_gate([{"status": "known"}], 0)["eligible"] is True


def test_complete_inventory_retains_unstarted_and_rejects_duplicate_slots(study):
    plan = _small(study)
    trial = study.trial_schedule(plan)[0]
    slots = study.slots_for(plan, trial)
    rows = study.complete_receipts(slots, [{"slot": slots[0], "status": "known"}])
    assert len(rows) == 6
    assert [row["status"] for row in rows] == ["known"] + ["unstarted"] * 5
    with pytest.raises(ValueError, match="Duplicate"):
        study.complete_receipts(slots, [rows[0], rows[0]])


def test_lossless_gzip_is_reproducible_and_exclusive(study, tmp_path):
    first, second = tmp_path / "first.json.gz", tmp_path / "second.json.gz"
    value = {"retained": [None, False, {"unknown": True}]}
    study.write_new_gzip(first, value)
    study.write_new_gzip(second, value)
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(gzip.decompress(first.read_bytes())) == value
    with pytest.raises(FileExistsError):
        study.write_new_gzip(first, {"changed": True})


def test_summary_uses_available_and_planned_denominators_separately(study):
    trial = {"mechanism": "refund-p50-q50", "method": "shapley"}
    rows = [{"trial": trial, "variants": {"native": [{"position": 0, "point": -.125, "interval": [-.2, 0.]}]}},
            {"trial": trial, "variants": {"native": []}}]
    result = study.summarize(rows, {"refund-p50-q50": study.exact_reference("refund-p50-q50")})
    first = result["rows"][0]
    assert first["available"] == first["scored"] == first["covered"] == 1
    assert first["coverage_available"] == 1.
    assert first["coverage_planned"] == .5
    assert result["rows"][1]["coverage_available"] is None


@pytest.mark.parametrize("method", ("contrastive", "shapley"))
@pytest.mark.parametrize("mechanism", ("refund-p50-q50", "refund-p20-q80", "refund-p80-q20",
                                      "refund-p100-q100", "idempotent-p50-q50"))
def test_unmodified_native_engine_matches_cx_draws_points_and_actual_calls(study, car, method, mechanism):
    plan = _small(study, mechanism)
    trial = next(row for row in study.trial_schedule(plan) if row["method"] == method)
    native = study.run_trial(car, plan, trial, "upstream_car")
    cx = study.run_trial(car, plan, trial, "consequa_x")
    audit = study.compare_pair(native, cx)
    assert audit["same_factual_trace"] and audit["same_actual_calls"]
    assert not audit["mismatches"]
    assert native["gate"]["eligible"] and cx["gate"]["eligible"]
    assert native["execution_cost"]["live_model_calls"] == 0
    assert native["execution_cost"]["deterministic_glue_world_runs"] > len(native["receipts"])
    native_points = [row["point"] for row in next(iter(native["variants"].values()))]
    for values in cx["variants"].values():
        assert [row["point"] for row in values] == pytest.approx(native_points)
    if method == "shapley":
        assert native["execution_cost"]["native_budget_charged_path_rollouts"] == 16
        assert native["execution_cost"]["supplemental_endpoint_rollouts"] == 4
        for native_row, cx_row in zip(native["variants"]["upstream_normal"], cx["variants"]["cx_normal"], strict=True):
            assert native_row["interval"] == pytest.approx(cx_row["interval"])


@pytest.mark.parametrize("method", ("contrastive", "shapley"))
def test_lagged_readback_refuses_every_primary_numeric_vector(study, car, method):
    plan = _small(study, "lagged-readback-p50-q50")
    trial = next(row for row in study.trial_schedule(plan) if row["method"] == method)
    for engine in study.ENGINES:
        row = study.run_trial(car, plan, trial, engine)
        assert row["gate"]["eligible"] is False
        assert all(not values for values in row["variants"].values())
        assert row["gate"]["counts"] == {"unknown": len(row["receipts"])}
        if engine == "upstream_car":
            assert row["unfiltered_native_diagnostic"] is not None
            assert row["unfiltered_diagnostic_eligible_for_inference"] is False


def test_missing_provenance_is_retained_and_refuses_linked_inference(study, car):
    plan = study.StudyPlan(repeats=1, samples=32, pairs=2, endpoint_samples=2, seed=80_000_000,
                           mechanisms=("unknown-provenance-p50-q50",))
    trial = study.trial_schedule(plan)[0]
    native = study.run_trial(car, plan, trial, "upstream_car")
    cx = study.run_trial(car, plan, trial, "consequa_x")
    assert not study.compare_pair(native, cx)["mismatches"]
    for row in (native, cx):
        assert row["gate"]["counts"]["unknown"] > 0
        assert not row["gate"]["eligible"]
        assert all(not values for values in row["variants"].values())
        assert any(draw.get("target_values", {}).get("consequence") is True
                   and draw.get("target_values", {}).get("action_linked_consequence") is None
                   for draw in row["receipts"])


@pytest.mark.parametrize("method", ("contrastive", "shapley"))
def test_budget_control_keeps_failed_unstarted_draws_and_no_partial_estimate(study, car, method):
    plan = _small(study, "budget-p50-q50")
    trial = next(row for row in study.trial_schedule(plan) if row["method"] == method)
    for engine in study.ENGINES:
        row = study.run_trial(car, plan, trial, engine)
        assert row["calls"]["total"] <= 4
        assert row["gate"]["eligible"] is False
        assert all(not values for values in row["variants"].values())
        assert row["gate"]["counts"].get("unstarted", 0) > 0
        assert sum(draw["policy_calls"] for draw in row["receipts"]) == row["calls"]["continuation"]


def test_changed_frozen_protocol_refuses_before_import_or_output(study, tmp_path, monkeypatch):
    protocol = study.make_protocol(_small(study), "0" * 40)
    protocol["source_files"] = {}
    monkeypatch.setattr(study, "load_car", lambda _: pytest.fail("must refuse before loading external code"))
    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="frozen local source hashes"):
        study.run_protocol(protocol, destination, "irrelevant")
    assert not destination.exists()


def test_changed_declared_reference_refuses_before_collection(study, tmp_path, monkeypatch):
    protocol = study.make_protocol(_small(study), "0" * 40)
    protocol["references"]["refund-p50-q50"]["shapley"][0] = 999
    monkeypatch.setattr(study, "load_car", lambda _: pytest.fail("must refuse before loading external code"))
    with pytest.raises(ValueError, match="complete declared design"):
        study.run_protocol(protocol, tmp_path / "must-not-exist", "irrelevant")


def test_protocol_binds_tests_documentation_interpreter_and_dependencies(study):
    protocol = study.make_protocol(_small(study), "0" * 40)
    assert "tests/test_upstream_car_study.py" in protocol["source_files"]
    assert "docs/upstream-car-comparison.md" in protocol["source_files"]
    assert protocol["execution_environment"]["python_version"] == sys.version
    assert set(protocol["execution_environment"]["dependencies"]) == {"numpy", "scipy", "pydantic", "structlog"}


def test_changed_dependency_version_refuses_before_external_import(study, tmp_path, monkeypatch):
    protocol = study.make_protocol(_small(study), "0" * 40)
    protocol["execution_environment"]["dependencies"]["numpy"] = "changed-after-freeze"
    monkeypatch.setattr(study, "load_car", lambda _: pytest.fail("must refuse before loading external code"))
    with pytest.raises(ValueError, match="complete declared design"):
        study.run_protocol(protocol, tmp_path / "must-not-exist", "irrelevant")


def test_changed_environment_during_collection_prevents_completion(study, monkeypatch):
    protocol = study.make_protocol(_small(study), "0" * 40)
    changed = deepcopy(protocol["execution_environment"])
    changed["dependencies"]["scipy"] = "changed-after-collection-began"
    monkeypatch.setattr(study, "dependency_fingerprint", lambda: changed)
    with pytest.raises(ValueError, match="changed during collection"):
        study.verify_final_bindings(protocol, {})


def test_serial_and_spawned_parallel_groups_have_identical_semantics(study, car):
    source = os.environ["CONSEQUAX_CAR_SOURCE"]
    plan = _small(study, workers=1)
    trials = study.trial_schedule(plan)
    serial = list(study.iter_group_results(plan, trials, source))
    parallel = list(study.iter_group_results(replace(plan, workers=2), trials, source))
    def by_index(rows):
        return {row["trial"]["group_index"]: row for row in rows}

    serial_by_index, parallel_by_index = by_index(serial), by_index(parallel)
    assert set(serial_by_index) == set(parallel_by_index) == {0, 1}
    for index in serial_by_index:
        assert serial_by_index[index]["status"] == parallel_by_index[index]["status"] == "completed"
        assert study.semantic_group_digest(serial_by_index[index]) == study.semantic_group_digest(parallel_by_index[index])


def test_group_failure_retains_completed_engine_and_does_not_redraw(study, monkeypatch):
    plan = _small(study, workers=1)
    trial = study.trial_schedule(plan)[0]
    calls = []
    def fake_run(car, plan, trial, engine):
        calls.append(engine)
        if engine == "consequa_x":
            raise RuntimeError("declared integration failure")
        return {"retained_engine": engine}
    monkeypatch.setattr(study, "run_trial", fake_run)
    result = study._compute_group(plan, trial)
    assert result["status"] == "failed"
    assert result["engine_rows"] == [{"retained_engine": "upstream_car"}]
    assert calls == ["upstream_car", "consequa_x"]


def test_serial_dispatch_stops_after_failure_without_starting_later_groups(study, monkeypatch):
    plan = _small(study, workers=1)
    trials = study.trial_schedule(plan)
    calls = []
    monkeypatch.setattr(study, "_initialize_worker", lambda *args: None)
    def fail_group(plan, trial):
        calls.append(trial["group_index"])
        return {"trial": trial, "status": "failed", "engine_rows": []}
    monkeypatch.setattr(study, "_compute_group", fail_group)
    results = list(study.iter_group_results(plan, trials, "not-used"))
    assert len(results) == 1 and calls == [0]


def test_declared_git_revision_must_contain_every_frozen_file(study, monkeypatch):
    protocol = study.make_protocol(_small(study), "0" * 40)
    monkeypatch.setattr(study.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    with pytest.raises(ValueError, match="absent from the declared Git revision"):
        study.verify_local_revision(protocol)
