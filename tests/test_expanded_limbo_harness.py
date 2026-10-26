"""Engineering fixtures only: no upstream task or model execution."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from research.expanded_limbo import harness
from research.expanded_limbo.protocol import file_binding


def test_policy_journal_preserves_nested_runtime_but_replays_only_top_level():
    saved, operations = [], []
    journal = harness.PolicyOperationJournal(saved.append)
    journal.active = operations
    journal({"event": "enter", "id": 1, "parent": None, "op": "execute",
             "args": ["write", {"value": 2}], "kwargs": {"source": "agent", "note": None}})
    journal({"event": "enter", "id": 2, "parent": 1, "op": "advance", "args": [5], "kwargs": {}})
    journal({"event": "return", "id": 2, "result": None})
    journal({"event": "return", "id": 1, "result": {"ok": True}})
    journal({"event": "enter", "id": 3, "parent": None, "op": "verify",
             "args": ["write", {"value": 2}, 0], "kwargs": {"truth": False}})
    journal({"event": "raise", "id": 3, "type": "ValueError", "message": "fixture refusal"})
    assert len(saved) == 6
    assert len(operations) == 2
    assert operations[0]["op"] == "execute"
    assert operations[0]["outcome"] == {"event": "return", "result": {"ok": True}}
    assert operations[1]["kwargs"]["truth"] is False
    assert operations[1]["outcome"]["type"] == "ValueError"
    assert journal.pending == {}


@pytest.mark.parametrize("raises", [False, True])
def test_policy_record_retains_start_outcome_clock_and_intervention_snapshot(raises):
    runtime = SimpleNamespace(world=SimpleNamespace(clock=10))
    policy = SimpleNamespace(name="fixture", prompt_variant="vanilla", reflect=False, interventions=[])

    def execute(rt, name, args):
        rt.world.clock += 3
        policy.interventions.append({"kind": "fixture decision", "name": name})
        if raises:
            raise ValueError("fixture policy error")
        return {"ok": True, "value": args["value"]}

    policy.execute = execute
    starts, completed = [], []
    recorder = harness.PolicyOperationJournal(lambda row: None)
    wrapped = harness.RecordedPolicy(policy, recorder, starts.append, completed.append)
    if raises:
        with pytest.raises(ValueError, match="fixture policy error"):
            wrapped.execute(runtime, "write", {"value": 9})
    else:
        assert wrapped.execute(runtime, "write", {"value": 9}) == {"ok": True, "value": 9}
    assert starts[0]["sequence"] == completed[0]["sequence"] == 1
    assert completed[0]["clock_before"] == 10 and completed[0]["clock_after"] == 13
    assert completed[0]["outcome"]["event"] == ("raise" if raises else "return")
    policy.interventions[0]["kind"] = "changed after recording"
    assert completed[0]["interventions"][0]["kind"] == "fixture decision"
    assert recorder.active is None


def test_policy_record_refuses_nested_calls():
    recorder = harness.PolicyOperationJournal(lambda row: None)
    recorder.active = []
    wrapped = harness.RecordedPolicy(SimpleNamespace(name="fixture", prompt_variant="vanilla",
        reflect=False, interventions=[]), recorder, lambda row: None, lambda row: None)
    with pytest.raises(ValueError, match="Nested"):
        wrapped.execute(SimpleNamespace(), "write", {})


def test_readiness_must_be_passed_exact_bytes_and_protocol_inputs(tmp_path):
    protocol = {"sources": {"source.py": {"sha256": "a" * 64, "bytes": 1}},
        "native_sources": {}, "wheel": {}, "models": [], "limits": {"max_requests": 16}}
    receipt = {"schema": "conseqax-expanded-limbo-readiness-v1", "passed": True, **protocol}
    path = tmp_path / "readiness.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    protocol["readiness"] = file_binding(path)
    assert harness.verify_readiness(protocol, path) == receipt
    altered = deepcopy(protocol)
    altered["limits"]["max_requests"] = 17
    with pytest.raises(ValueError, match="limits"):
        harness.verify_readiness(altered, path)
    protocol["readiness"] = None
    with pytest.raises(ValueError, match="readiness-free"):
        harness.verify_readiness(protocol, path)


@pytest.fixture
def block_fixture(tmp_path, monkeypatch):
    source = tmp_path / "source.py"
    source.write_text("# synthetic fixture\n", encoding="utf-8")
    protocol_path, runtime_path, wheel_path = [tmp_path / n for n in ("protocol.json", "lease.json", "wheel.whl")]
    for path in (protocol_path, runtime_path, wheel_path):
        path.write_text("{}", encoding="utf-8")
    block = {"block_id": "block-0000", "model_id": "fixture-model", "first_slot": 0, "slot_count": 3}
    protocol = {"sources": {"source.py": file_binding(source)}, "wheel": file_binding(wheel_path),
        "blocks": [block], "schedule": [{"slot": i, "block_id": "block-0000"} for i in range(3)],
        "counts": {"planned_slots": 3456}, "limits": {"episode_timeout_s": 60}}
    monkeypatch.setattr(harness, "committed_protocol", lambda *a, **k: protocol)
    monkeypatch.setattr(harness, "verify_readiness", lambda *a: None)
    monkeypatch.setattr(harness, "verify_native", lambda *a: None)
    monkeypatch.setattr(harness, "installed_wheel_binding", lambda *a: None)
    monkeypatch.setattr(harness, "bound_runtime", lambda *a: None)
    return tmp_path, protocol_path, runtime_path, wheel_path, protocol


def collect(fixture, output, **kwargs):
    root, protocol, runtime, wheel, _ = fixture
    return harness.collect_block(root, root, protocol, "a" * 40, wheel,
        runtime, "block-0000", output, **kwargs)


def test_one_block_reservation_cannot_be_bypassed_with_a_different_output(block_fixture, monkeypatch):
    root = block_fixture[0]
    seen = []

    def execute(root, native, config, output, limits):
        seen.append(config["slot"])
        output.mkdir()
        return {"slot": config["slot"], "block_id": "block-0000", "status": "child_returned"}

    monkeypatch.setattr(harness, "execute_slot", execute)
    result = collect(block_fixture, root / "out-one")
    assert seen == [0, 1, 2]
    assert result["planned"] == 3
    sealed = harness.load(root / "out-one/collection.json")
    assert sealed["entire_matrix_planned"] == 3456
    assert sealed["block_planned"] == 3
    with pytest.raises(FileExistsError):
        collect(block_fixture, root / "out-two")
    assert not (root / "out-two").exists()
    assert seen == [0, 1, 2]


def test_runtime_lease_change_stops_later_slots_without_replacement(block_fixture, monkeypatch):
    root, _, runtime_path, _, _ = block_fixture
    seen = []

    def execute(root, native, config, output, limits):
        seen.append(config["slot"])
        output.mkdir()
        runtime_path.write_text('{"changed": true}', encoding="utf-8")
        return {"slot": config["slot"], "block_id": "block-0000", "status": "child_returned"}

    monkeypatch.setattr(harness, "execute_slot", execute)
    result = collect(block_fixture, root / "out")
    assert seen == [0]
    assert [r["status"] for r in result["rows"]] == [
        "child_returned", "unstarted_integrity_stop", "unstarted_integrity_stop"]
    assert "Lease changed" in harness.load(root / "out/collection.json")["stopped_reason"]


def test_parent_failure_retains_partial_prefix_and_all_block_denominators(block_fixture, monkeypatch):
    root = block_fixture[0]

    def execute(root, native, config, output, limits):
        output.mkdir()
        (output / "prefix.jsonl").write_text('{"fixture":true}\n', encoding="utf-8")
        raise RuntimeError("fixture interrupted parent")

    monkeypatch.setattr(harness, "execute_slot", execute)
    result = collect(block_fixture, root / "out")
    assert [r["slot"] for r in result["rows"]] == [0, 1, 2]
    assert result["rows"][0]["status"] == "started_parent_error"
    assert all(r["status"] == "unstarted_integrity_stop" for r in result["rows"][1:])
    sealed = harness.load(root / "out/manifest.json")
    assert "slot-00000/prefix.jsonl" in sealed
    assert harness.load(root / "out/collection.json")["no_retry_resume_replacement"] is True


def test_keyboard_interrupt_still_seals_all_planned_dispositions(block_fixture, monkeypatch):
    root = block_fixture[0]

    def execute(root, native, config, output, limits):
        output.mkdir()
        raise KeyboardInterrupt()

    monkeypatch.setattr(harness, "execute_slot", execute)
    with pytest.raises(KeyboardInterrupt):
        collect(block_fixture, root / "out")
    rows = harness.load(root / "out/collection.json")["rows"]
    assert len(rows) == 3 and len({r["slot"] for r in rows}) == 3
    assert rows[0]["status"] == "started_parent_error"
    assert all(r["status"] == "unstarted_after_collector_interruption" for r in rows[1:])


def test_source_inventory_refuses_a_path_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("# fixture", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        harness.verify_files(root, {"../outside.py": file_binding(outside)})


def test_inventory_includes_new_policy_and_frozen_dependencies(tmp_path):
    names = ["research/expanded_limbo/protocol.py", "research/expanded_limbo/transport.py",
        "research/obligation_shield/policy.py", "research/limbo_agent/harness.py",
        "research/native_agent/transport.py", "research/native_agent/__init__.py",
        "scripts/run_expanded_limbo.py"]
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic fixture\n", encoding="utf-8")
    assert set(harness.scientific_sources(tmp_path)) == set(names)
