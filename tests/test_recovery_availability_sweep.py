"""Synthetic development checks; never execute a measured factorial cell."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("availability_sweep", ROOT / "scripts/run_recovery_availability_sweep.py")
sweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep)


def development_case(domain="delivery_registration"):
    # These factor values are outside the measured {0,40,80,95} x {0,170,210,250} grid.
    return sweep.controlled_case(domain, 17, 101, 117, prefix="synthetic-development")


def protocol_fixture():
    cases = sweep.generated_cases()
    return {"schema": sweep.SCHEMA, "case_count": 192, "profile_count": 64, "domain_count": 3, "seed_count": 1,
            "methods": list(sweep.METHODS), "cases": cases, "schedule": sweep.schedule(cases),
            "cases_json": {**sweep.byte_binding(sweep.json_bytes({"schema": sweep.SCHEMA, "cases": cases})),
                           "git_path": "output/development/cases.json"}}


def test_declared_grid_is_complete_unique_and_unexecuted():
    cases = sweep.generated_cases()
    sweep.validate_cases(cases)
    assert len(cases) == 192
    profiles = {case["family_id"] for case in cases}
    assert len(profiles) == 64
    assert {case["domain"] for case in cases} == set(sweep.DOMAINS)
    for domain in sweep.DOMAINS:
        seen = {(c["_availability_profile"]["lag_ms"], c["_availability_profile"]["unavailable_until_ms"],
                 c["_availability_profile"]["incomplete_until_ms"]) for c in cases if c["domain"] == domain}
        assert seen == {(a, b, c) for a in sweep.LAGS for b in sweep.WINDOW_ENDS for c in sweep.WINDOW_ENDS}


def test_schedule_is_matched_rotated_and_one_seed_only():
    cases = sweep.generated_cases()
    rows = sweep.schedule(cases)
    assert len(rows) == 960 and len({row["trial_id"] for row in rows}) == 960
    assert {row["seed"] for row in rows} == {0}
    for index, case in enumerate(cases):
        block = rows[index * 5:index * 5 + 5]
        offset = index % 5
        assert [row["method"] for row in block] == list(sweep.METHODS[offset:] + sweep.METHODS[:offset])
        assert all(row["case_id"] == case["case_id"] and row["family_id"] == case["family_id"] for row in block)
        assert all({key: row[key] for key in case["_availability_profile"]} == case["_availability_profile"] for row in block)


@pytest.mark.parametrize("domain", sweep.DOMAINS)
def test_synthetic_case_uses_real_domain_public_boundary_and_independent_windows(tmp_path, domain):
    from research.recovery_study.world import World, public_case

    case = development_case(domain)
    assert not {"_world", "_availability_profile"} & public_case(case).keys()
    assert case["native_idempotency"] is True
    with World(case, 23, tmp_path / "development.sqlite") as world:
        response = world.dispatch(case["operation_id"], case["actor"], 0)
        assert response["status"] == "success" and response["response_at_ms"] == 2
        unavailable = world.readback(100)
        incomplete = world.readback(105)
        admitted = world.readback(120)
        assert unavailable["available"] is False
        assert incomplete["available"] is True and incomplete["complete"] is False
        assert admitted["available"] is True and admitted["complete"] is True
        assert admitted["as_of_ms"] == 103
        assert admitted["source"] == world.source_receipt["source"]
        assert admitted["scope"] == case["scope"]
        assert len(admitted["records"]) == 1
        truth = world.truth(330)
        assert truth["target_satisfied"] is True
        assert truth["eventual_recovery_satisfied"] is True
        assert truth["own_effect_count"] == 1
        assert truth["duplicate_count"] == truth["own_unwanted_effect_count"] == 0


@pytest.mark.parametrize("method", sweep.METHODS)
def test_unchanged_driver_synthetic_only_matching_no_extra_dispatch(tmp_path, method):
    engine = sweep.load_engine()
    case = development_case()
    row = engine.execute(case, 23, method, tmp_path / f"{method}.sqlite")
    assert row["status"] == "completed", row
    assert row["metrics"]["operational_safe_recovery"] is True
    assert row["metrics"]["original_completion"] is True
    assert row["metrics"]["dispatches"] == 1
    assert row["metrics"]["duplicate_event"] is False
    assert row["metrics"]["unwanted_event"] is False
    assert row["controller_inputs"]["native_idempotency"] is True
    assert row["controller_inputs"]["read_times"] == [50, 150, 190, 230]
    assert not {"_world", "_availability_profile", "seed", "domain", "truth", "family_id", "case_id"} & row["controller_inputs"].keys()


def test_synthetic_intersection_uses_watermark_and_both_window_ends(tmp_path):
    from research.recovery_study.world import World

    case = sweep.controlled_case("support_transition", 19, 183, 207, prefix="synthetic-intersection")
    with World(case, 23, tmp_path / "intersection.sqlite") as world:
        world.dispatch(case["operation_id"], case["actor"], 0)
        first = world.readback(175)
        second = world.readback(195)
        final = world.readback(225)
        assert first["as_of_ms"] >= 150 and first["available"] is False
        assert second["as_of_ms"] >= 150 and second["available"] is True and second["complete"] is False
        assert final["as_of_ms"] >= 150 and final["available"] is True and final["complete"] is True


@pytest.mark.parametrize("change", ["omit_case", "payload", "lag", "native", "window"])
def test_grid_rejects_post_freeze_case_edits(change):
    cases = sweep.generated_cases()
    if change == "omit_case":
        cases.pop()
    elif change == "payload":
        cases[0]["payload"]["quantity"] = 5
    elif change == "lag":
        cases[0]["_world"]["readback"]["lag_ms"] = 1
    elif change == "native":
        cases[0]["native_idempotency"] = False
    else:
        cases[0]["_world"]["readback"]["windows"].append({"available": False})
    with pytest.raises(ValueError, match="controlled grid"):
        sweep.validate_cases(cases)


def test_protocol_binding_checks_exact_json_and_schedule():
    protocol = protocol_fixture()
    sweep.validate_protocol(protocol)
    edited = deepcopy(protocol)
    edited["schedule"][0]["seed"] = 1
    with pytest.raises(ValueError, match="schedule"):
        sweep.validate_protocol(edited)
    edited = deepcopy(protocol)
    edited["cases_json"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="byte binding"):
        sweep.validate_protocol(edited)


@pytest.mark.parametrize("name,value", [("case_count", 191), ("profile_count", 63),
                                       ("domain_count", 2), ("seed_count", 128)])
def test_protocol_rejects_inconsistent_declared_dimensions(name, value):
    protocol = protocol_fixture()
    protocol[name] = value
    with pytest.raises(ValueError, match="dimensions"):
        sweep.validate_protocol(protocol)


def test_canonical_json_preserves_actual_newline_and_strict_numbers():
    value = sweep.json_bytes({"a": "two\nlines"})
    assert value.endswith(b"\n") and json.loads(value) == {"a": "two\nlines"}
    with pytest.raises(ValueError):
        sweep.json_bytes({"bad": float("nan")})


@pytest.mark.parametrize("domain,lag,end", [("bad", 17, 101), ("support_transition", -1, 101),
                                          ("support_transition", True, 101), ("support_transition", 17, -1)])
def test_case_generator_rejects_unsupported_domain_and_delay_types(domain, lag, end):
    with pytest.raises(ValueError):
        sweep.controlled_case(domain, lag, end, 117)


def test_canonical_claim_cannot_be_bypassed_by_copying_protocol(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "ROOT", tmp_path / "frozen-source")
    protocol = {"source": {"commit": "development-only"}, "protocol_git_path": "output/dev/protocol.json",
                "cases_json": {"git_path": "output/dev/cases.json"}}
    first = sweep.reserve_run(tmp_path / "original/protocol.json", protocol, "a" * 64,
                              tmp_path / "output", tmp_path / "databases", "dev-protocol")
    assert first["retry_allowed"] is False
    assert first["database_root"] == str((tmp_path / "databases").resolve())
    assert first["canonical_claim_path"].endswith(f"{'a' * 64}.json")
    with pytest.raises(FileExistsError):
        sweep.reserve_run(tmp_path / "copy/protocol.json", protocol, "a" * 64,
                          tmp_path / "other-output", tmp_path / "other-databases", "dev-protocol")


@pytest.mark.parametrize("nested", ["same", "output-child", "database-child"])
def test_output_and_database_roots_cannot_overlap(tmp_path, nested):
    output = tmp_path / "new-output"
    database = output if nested == "same" else output / "child" if nested == "output-child" else tmp_path
    with pytest.raises(ValueError, match="nonnested"):
        sweep.validate_roots(output, database)


def test_existing_output_is_never_reused(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="both be new"):
        sweep.validate_roots(existing, tmp_path / "new")


def test_other_checkout_cannot_claim_the_frozen_root(tmp_path):
    with pytest.raises(ValueError, match="Executing checkout"):
        sweep.verify_frozen({"source": {"root": str(tmp_path)}})


def test_engine_binding_rejects_any_original_source_change(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "ENGINE_FILES", ("engine.py",))
    (tmp_path / "engine.py").write_bytes(b"changed\n")
    monkeypatch.setattr(sweep, "git_blob", lambda *args: b"committed-original\n")
    with pytest.raises(ValueError, match="engine changed"):
        sweep.engine_binding(tmp_path)


def test_runtime_rejects_source_checkout_package(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "consequa_x", SimpleNamespace(__file__=str(tmp_path / "src/consequa_x/__init__.py")))
    monkeypatch.setattr(sweep.sysconfig, "get_paths", lambda: {"purelib": str(tmp_path / "installed")})
    with pytest.raises(ValueError, match="installed distribution"):
        sweep.runtime()


def test_runtime_rejects_non_211_distribution(tmp_path, monkeypatch):
    import sys

    package = tmp_path / "site-packages/consequa_x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"__version__='9.9.9'\n")
    monkeypatch.setitem(sys.modules, "consequa_x", SimpleNamespace(__file__=str(package / "__init__.py"), __version__="9.9.9"))
    monkeypatch.setattr(sweep.sysconfig, "get_paths", lambda: {"purelib": str(package.parent)})
    monkeypatch.setattr(sweep.importlib.metadata, "version", lambda name: "9.9.9")
    with pytest.raises(ValueError, match="2.1.1"):
        sweep.runtime()


def test_protocol_hash_failure_occurs_before_any_import_claim_or_execution(tmp_path, monkeypatch):
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text('{}\n', encoding="utf-8")
    touched = []
    monkeypatch.setattr(sweep, "verify_frozen", lambda *a: touched.append("verify"))
    monkeypatch.setattr(sweep, "load_engine", lambda: touched.append("execute"))
    args = SimpleNamespace(protocol=protocol_path, expected_protocol_sha256="0" * 64)
    with pytest.raises(ValueError, match="hash mismatch"):
        sweep.run(args)
    assert not touched


def test_prospective_commit_requires_exact_committed_case_bytes(monkeypatch):
    protocol = {"source": {"commit": "dev-source"}, "protocol_git_path": "output/dev/protocol.json",
                "cases_json": {**sweep.byte_binding(b"correct-cases"), "git_path": "output/dev/cases.json"}}
    protocol_bytes = b"development-protocol"
    monkeypatch.setattr(sweep.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(sweep, "git_blob", lambda root, commit, path:
                        protocol_bytes if path.endswith("protocol.json") else b"changed-cases")
    with pytest.raises(ValueError, match="case JSON"):
        sweep.verify_prospective_commit(protocol, hashlib.sha256(protocol_bytes).hexdigest(), "dev-protocol")


def test_original_aggregation_retains_failed_primary_and_unknown_semantics():
    engine = sweep.load_engine()
    rows = [{"status": "completed", "metrics": {"operational_safe_recovery": True, "safe_recovery": True}},
            {"status": "failed", "metrics": {"completed": False, "operational_safe_recovery": False}}]
    result = engine.aggregate(rows)
    assert result["metrics"]["operational_safe_recovery"]["mean"] == 0.5
    assert result["metrics"]["safe_recovery"]["unavailable"] == 1
