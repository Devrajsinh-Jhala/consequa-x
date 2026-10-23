"""Synthetic fixtures and invented worlds only; no benchmark task scores."""
from __future__ import annotations

import copy
import importlib
import json
import os
from pathlib import Path

import pytest

from scripts import check_limbo_saved_proposal_receipt as check


def public_event(name="db_insert_many", arguments=None):
    return {"event": "enter", "op": "execute", "id": 4, "parent": None,
            "args": [name, arguments or {"table": "invented", "rows": [{"name": "a"}]}],
            "kwargs": {"source": "agent", "note": ""}, "clock": 0.0}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def seal_directory(path):
    write_json(path / "manifest.json", check.harness.manifest(path))


def test_selects_first_saved_public_dispatch_without_outcome_filtering():
    first, later = public_event(), public_event("different", {"later": True})
    events = [{"event": "return", "id": 2}, first, later]
    before = copy.deepcopy(events)
    proposal = check.select_saved_proposal(events)
    assert proposal["name"] == first["args"][0] and proposal["line_number"] == 2
    assert proposal["arguments"] == first["args"][1]
    proposal["arguments"]["rows"].clear()
    assert events == before


@pytest.mark.parametrize("events,match", [
    ([], "no original public"),
    ([{**public_event(), "parent": 1}], "original agent"),
    ([{**public_event(), "kwargs": {"source": "guard"}}], "original agent"),
    ([{**public_event(), "args": ["tool", []]}], "invalid shape"),
])
def test_invalid_first_dispatch_is_not_silently_replaced(events, match):
    with pytest.raises(ValueError, match=match):
        check.select_saved_proposal(events)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    root, native, development, audit_dir = [tmp_path / name for name in ("root", "native", "episode", "audit")]
    for directory in (root, native, development, audit_dir):
        directory.mkdir()
    (root / "docs").mkdir()
    (root / check.AMENDMENT).write_text("Synthetic prospective amendment.\n", encoding="utf-8")
    (root / "probe.py").write_text("# Synthetic source\n", encoding="utf-8")
    wheel = root / "synthetic.whl"
    wheel.write_bytes(b"synthetic wheel fixture")
    source = {"probe.py": check.protocol.file_binding(root / "probe.py")}
    native_identity, environment, installed = {"commit": "synthetic", "files": {}}, {"synthetic": True}, {"synthetic": True}
    monkeypatch.setattr(check.protocol, "source_binding", lambda _root: source)
    monkeypatch.setattr(check.protocol, "native_binding", lambda _root: native_identity)
    monkeypatch.setattr(check.protocol, "environment_binding", lambda: environment)
    monkeypatch.setattr(check, "audit_framework_wheel", lambda _wheel: installed)
    spec = {"policy": "conseqax_guard", "index": 0, "mode": "timeout_post", "human_available": False}
    slot = {"slot": 0, "world_rank": 0, "arm": "conseqax_guard", "spec": spec}
    frozen = {"sources": source, "native": native_identity, "environment": environment,
              "wheel": {"path": str(wheel), **check.protocol.file_binding(wheel)}}
    config = {"protocol": frozen, "slot": slot}
    write_json(development / "worker-config.json", config)
    write_json(development / "installed-wheel.json", installed)
    (development / "runtime.jsonl").write_text(json.dumps(public_event()) + "\n", encoding="utf-8")
    row = {"slot": 0, "world_rank": 0, "arm": "conseqax_guard", "started": True,
        "operational": True, "audit_complete": True, "grade_available": True,
        "execution_success": True, "fault_triggered": True, "status": "audited_native_return"}
    value = {"schema": "conseqax-limbo-development-audit-v1", "passed": True,
        "episode": str(development), "sources": source, "native": native_identity, "spec": spec, "row": row}
    audit_path = audit_dir / "audit-result.json"
    def seal():
        write_json(development / "worker-config.json", config)
        seal_directory(development)
        value["episode_manifest"] = check.protocol.file_binding(development / "manifest.json")
        write_json(audit_path, value)
        seal_directory(audit_dir)
    seal()
    return {"root": root, "native": native, "wheel": wheel, "development": development,
            "audit": audit_path, "value": value, "config": config, "seal": seal}


def validate(inputs):
    return check.validate_inputs(inputs["root"], inputs["native"], inputs["wheel"],
                                 inputs["development"], inputs["audit"])


def test_full_input_bindings_checked_on_synthetic_fixture(inputs):
    frozen, spec, proposal, installed, provenance = validate(inputs)
    assert spec["index"] == 0 and proposal["name"] == "db_insert_many"
    assert installed == {"synthetic": True}
    assert frozen == inputs["config"]["protocol"]
    assert provenance["source_audit"]["sha256"] == check.protocol.file_binding(inputs["audit"])["sha256"]


@pytest.mark.parametrize("mutation,match", [
    (lambda data: data["value"].update(passed=False), "Passed complete"),
    (lambda data: data["value"]["row"].update(execution_success=False), "complete normal"),
    (lambda data: data["value"]["row"].update(fault_triggered=False), "fault did not trigger"),
    (lambda data: data["config"]["slot"]["spec"].update(index=10000), "excluded guarded"),
])
def test_readiness_evidence_cannot_be_substituted(inputs, mutation, match):
    mutation(inputs)
    inputs["seal"]()
    with pytest.raises(ValueError, match=match):
        validate(inputs)


def test_amendment_source_and_unsealed_episode_are_required(inputs):
    amendment = inputs["root"] / check.AMENDMENT
    amendment.rename(amendment.with_suffix(".absent"))
    with pytest.raises(ValueError, match="amendment must exist"):
        validate(inputs)
    amendment.with_suffix(".absent").rename(amendment)
    (inputs["root"] / "probe.py").write_text("# Changed source\n", encoding="utf-8")
    with pytest.raises(ValueError, match="File identity changed"):
        validate(inputs)


@pytest.fixture
def native(monkeypatch):
    root = os.environ.get("CONSEQAX_LIMBO_ROOT")
    if not root:
        pytest.skip("Set CONSEQAX_LIMBO_ROOT for unchanged native invented-world integration tests")
    monkeypatch.syspath_prepend(str(Path(root).resolve()))
    return {name: importlib.import_module("limbo." + name) for name in ("world", "runtime", "services", "policies")}


def test_actual_scripted_reissue_receipt_and_exact_native_parity_on_invented_world(native, tmp_path, monkeypatch):
    cx = pytest.importorskip("consequa_x")
    if cx.__version__ != "2.1.1":
        pytest.skip("Selected 2.1.1 wheel required")
    def invented_runtime(_spec):
        world = native["world"].World(seed=123, human_available=False)
        world.tables = {"invented"}
        return native["runtime"].ToolRuntime(world, native["services"].build_tools("native"),
            [native["runtime"].FaultSpec("timeout_post", "db_insert_many")]), "same-invented-episode"
    monkeypatch.setattr(check, "fresh_runtime", invented_runtime)
    proposal = check.select_saved_proposal([public_event()])
    limits = {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800}
    with check.audit.no_network():
        reference = check.execute_arm(tmp_path / "native", {}, proposal, limits, package=False)
        package = check.execute_arm(tmp_path / "package", {}, proposal, limits, package=True)
    receipts, parity = check.compare_arms(reference, package)
    assert receipts == 1 and parity == {key: True for key in check.PARITY_FIELDS}
    assert len(package["observations"]) == 2 and package["fault_triggered"] is True
    assert all(row["receipt"]["verification"]["origin"] == "unknown" for row in package["framework_events"]
               if row.get("operation") == "package_receipt")
    for key in ("observations", "final_rng", "final_ledger"):
        corrupted = copy.deepcopy(package)
        corrupted[key] = ["synthetic mismatch"]
        with pytest.raises(ValueError, match="Native/SDK path differs"):
            check.compare_arms(reference, corrupted)
    corrupted = copy.deepcopy(package)
    corrupted["framework_events"] = []
    with pytest.raises(ValueError, match="real SDK receipt"):
        check.compare_arms(reference, corrupted)


def test_model_episode_and_grader_are_blocked_and_restored(native):
    from limbo import agent, grader, llm
    originals = (llm.LLMClient.__init__, agent.run_episode, grader.grade, agent.grade)
    with check.forbid_inference_and_grading() as counters:
        with pytest.raises(RuntimeError, match="Model clients are forbidden"):
            llm.LLMClient("forbidden")
        with pytest.raises(RuntimeError, match="Autonomous episodes are forbidden"):
            agent.run_episode(None)
        with pytest.raises(RuntimeError, match="Task grading is forbidden"):
            grader.grade(None, None)
    assert counters == {"model_constructor_attempts": 1, "native_episode_attempts": 1, "task_grade_attempts": 1}
    assert originals == (llm.LLMClient.__init__, agent.run_episode, grader.grade, agent.grade)
