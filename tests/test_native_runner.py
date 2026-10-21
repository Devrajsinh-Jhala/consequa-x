"""Prospective-runner integrity and failure tests; no model/corpus/network use."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts import run_native_external_benchmark as r


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.fixture
def args(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "actual_source_files", lambda: {"fixture.py": {"sha256": "a" * 64, "bytes": 1}})
    return SimpleNamespace(output=str(tmp_path / "output"), native_root=str(tmp_path / "native"),
        models=str(tmp_path / "models"), wheel=str(tmp_path / "wheel.whl"), server_launch=str(tmp_path / "launch.json"),
        development_ledger=str(tmp_path / "ledger"), development_reservation=None,
        development_reservation_sha256=None, task_id="19", arm="native", max_requests=18,
        timeout=3600, request_timeout=600, protocol=None, protocol_commit="b" * 40,
        protocol_sha256=None, slot=0)


def test_development_budget_preserves_manual_reservation_and_shared_ceiling(args):
    ledger = Path(args.development_ledger)
    ledger.mkdir()
    manual = ledger / "manual-transport-reservation-000.json"
    r.write_new(manual, {"category": "task_independent_transport", "reserved_maximum_requests": 2})
    before = manual.read_bytes()
    first = r.reserve_development(args, "task_independent_transport", 2)
    assert read(first)["consumed_before"] == 2
    assert manual.read_bytes() == before
    with pytest.raises(ValueError, match="allowance exhausted"):
        r.reserve_development(args, "task_independent_transport", 9)
    assert not (ledger / "exclusive-budget-lock").exists()


def test_development_budget_exclusive_lock_and_categories(args):
    first = r.reserve_development(args, "excluded_native", 18)
    assert read(first)["reserved_maximum_requests"] == 18
    r.reserve_development(args, "excluded_native", 18)
    with pytest.raises(ValueError, match="allowance exhausted"):
        r.reserve_development(args, "excluded_native", 1)
    r.reserve_development(args, "task_independent_transport", 2)
    lock = Path(args.development_ledger) / "exclusive-budget-lock"
    lock.mkdir()
    with pytest.raises(FileExistsError):
        r.reserve_development(args, "task_independent_transport", 1)
    assert lock.exists(), "A different owner's or stale lock must not be removed"


def test_development_settlement_releases_only_complete_accounted_attempts(args):
    reservation = r.reserve_development(args, "excluded_native", 18)
    output = Path(args.output)
    (output / "episode").mkdir(parents=True)
    r.write_new(output / "parent-receipt.json", {"exit_code": 1, "hard_timeout": False, "supervisor_error": None})
    r.write_new(output / "episode/execution-receipt.json", {"model_requests": {
        "attempted": 1, "completed": 0, "failed": 1}, "capture_errors": [], "inflight_tool_dispatches": []})
    calls = output / "episode/model-calls.jsonl"
    calls.write_text('\n'.join(json.dumps(row) for row in [
        {"kind": "request_start", "call_index": 0}, {"kind": "request_error", "call_index": 0}]) + '\n')
    assert r.settle_development(reservation, output)
    second = r.reserve_development(args, "excluded_native", 35)
    assert read(second)["consumed_before"] == 1
    calls.write_text("tampered")
    with pytest.raises(ValueError, match="artifact changed"):
        r.reserve_development(args, "excluded_native", 1)


def test_missing_or_partial_accounting_never_releases_budget(args):
    reservation = r.reserve_development(args, "excluded_native", 36)
    assert not r.settle_development(reservation, args.output)
    with pytest.raises(ValueError, match="allowance exhausted"):
        r.reserve_development(args, "excluded_native", 1)


def launch_configuration(tmp_path, parallel=2):
    blob = tmp_path / "models" / "blobs" / "model"
    launch = {"process_only_environment": {
        "OLLAMA_NUM_PARALLEL": str(parallel), "OLLAMA_HOST": "127.0.0.1:11436",
        "OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_FLASH_ATTENTION": "1",
        "OLLAMA_CONTEXT_LENGTH": "16384", "OLLAMA_NO_CLOUD": "1",
        "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_MODELS": str(blob.parents[1])}}
    command = ["llama-server.exe", "--model", str(blob), "--port", "50000", "--host", "127.0.0.1",
        "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "--flash-attn", "on",
        "-np", str(parallel), "-c", str(parallel * 16384), "--offline", "--context-shift"]
    return blob, launch, command


def test_actual_q8_runner_configuration_checks_per_slot_context(tmp_path):
    blob, launch, command = launch_configuration(tmp_path)
    result = r.verify_runner_configuration(command, blob, launch)
    assert result["cache_capacity_slots"] == 2 and result["context_tokens_per_slot"] == 16384
    command[command.index("-c") + 1] = "16384"
    with pytest.raises(ValueError, match="Actual model runner"):
        r.verify_runner_configuration(command, blob, launch)


@pytest.mark.parametrize("flag,value", [("--cache-type-k", "q4_0"), ("--cache-type-v", "f16"),
    ("--flash-attn", "off"), ("--host", "0.0.0.0"), ("-np", "3")])
def test_actual_runner_refuses_configuration_drift(tmp_path, flag, value):
    blob, launch, command = launch_configuration(tmp_path)
    command[command.index(flag) + 1] = value
    with pytest.raises(ValueError):
        r.verify_runner_configuration(command, blob, launch)


def test_worker_protocol_anchor_failure_exits_fatal_without_runtime(args, monkeypatch):
    args.protocol = "synthetic"
    monkeypatch.setattr(r, "verified_protocol", lambda args: (_ for _ in ()).throw(ValueError("anchor changed")))
    monkeypatch.setattr(r, "runtime_gate", lambda *a: pytest.fail("Invalid protocol reached runtime"))
    assert r.worker(args) == 78
    assert read(Path(args.output) / "startup-fatal.json")["integrity_exit_code"] == 78


def test_worker_official_ceilings_cannot_be_changed_by_cli(args, monkeypatch):
    args.protocol = "synthetic"
    protocol = {"schedule": [{"task_id": "synthetic", "arm": "B", "seed": 1701, "episode_id": "fixture"}],
        "ceilings": {"max_requests": 48, "max_steps": 80, "hard_slot_timeout_seconds": 3600,
                     "request_timeout_seconds": 600}}
    monkeypatch.setattr(r, "verified_protocol", lambda args: (protocol, {}))
    monkeypatch.setattr(r, "runtime_gate", lambda *a: pytest.fail("Different ceiling reached runtime"))
    args.max_requests = 49
    assert r.worker(args) == 78


@pytest.mark.parametrize("failure", ["timeout", "interrupt", "spawn"])
def test_supervisor_always_reaps_and_preserves_parent_receipt(args, monkeypatch, failure):
    args.development_reservation = "reservation"
    args.development_reservation_sha256 = "c" * 64

    class Process:
        pid = 10
        returncode = None
        killed = False
        waits = 0

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                if failure == "timeout":
                    raise subprocess.TimeoutExpired("fixture", timeout)
                raise KeyboardInterrupt("fixture interruption")
            assert self.killed
            self.returncode = -9
            return self.returncode

        def poll(self):
            return self.returncode

        def kill(self):
            self.killed = True

    process = Process()

    def spawn(*a, **kwargs):
        if failure == "spawn":
            raise OSError("fixture spawn failure")
        assert kwargs["env"]["PYTHONPATH"] == str(r.ROOT) + r.os.pathsep + str(Path(args.native_root) / "src")
        return process

    monkeypatch.setattr(r.subprocess, "Popen", spawn)
    assert r.supervise(args) == (124 if failure == "timeout" else 70)
    receipt = read(Path(args.output) / "parent-receipt.json")
    assert "native_reward_available" not in receipt and receipt["saved_simulation_available"] is False
    assert receipt["partial_artifacts_preserved"] is True
    if failure != "spawn":
        assert process.killed and process.waits == 2


@pytest.fixture
def collection(args, tmp_path, monkeypatch):
    args.protocol = str(tmp_path / "protocol" / "protocol.json")
    Path(args.protocol).parent.mkdir()
    schedule = [{"slot": index, "task_id": str(index // 4), "arm": "BCRG"[index % 4],
        "episode_id": "fixture-" + str(index), "seed": 1701} for index in range(48)]
    protocol = {"schedule": schedule, "source": {"files": {}}, "runtime": {}, "native": {},
        "readiness_receipt": {"path": "synthetic"}, "ceilings": {"max_requests": 48,
        "hard_slot_timeout_seconds": 3600, "request_timeout_seconds": 600}}
    anchor = {"protocol_commit": args.protocol_commit, "protocol_sha256": "d" * 64}
    monkeypatch.setattr(r, "verified_protocol", lambda a: (deepcopy(protocol), anchor))
    monkeypatch.setattr(r, "source_binding", lambda root: protocol["source"])
    monkeypatch.setattr(r, "runtime_binding", lambda wheel: protocol["runtime"])
    monkeypatch.setattr(r, "verify_native_binding", lambda *a: None)
    monkeypatch.setattr(r, "verify_readiness", lambda *a: None)
    monkeypatch.setattr(r, "runtime_gate", lambda *a: (SimpleNamespace(__exit__=lambda *a: None), None, {}))
    return args


@pytest.mark.parametrize("first_code,status", [(78, "integrity_failed"), (70, "supervisor_failed")])
def test_collection_fatal_startup_stops_and_preserves_all_slots(collection, monkeypatch, first_code, status):
    called = []

    def supervise(*a, **kwargs):
        called.append(kwargs["slot"])
        return first_code

    monkeypatch.setattr(r, "supervise", supervise)
    original = collection.output
    assert r.collect(collection) == 1 and collection.output == original
    receipt = read(Path(original) / "collection-receipt.json")
    assert receipt["protocol_commit"] == collection.protocol_commit
    assert len(receipt["all_planned_slots"]) == 48 and called == [0]
    assert receipt["all_planned_slots"][0]["status"] == status
    assert all(row["status"] == "unstarted" for row in receipt["all_planned_slots"][1:])
    assert len(list(Path(original).glob("disposition-*.json"))) == 48
    assert (Path(original) / "manifest.json").exists()


def test_collection_preserves_ordinary_failure_and_continues_fixed_matrix(collection, monkeypatch):
    calls = []

    def supervise(*a, **kwargs):
        calls.append(kwargs["slot"])
        return 1 if kwargs["slot"] == 0 else 0

    monkeypatch.setattr(r, "supervise", supervise)
    assert r.collect(collection) == 0
    receipt = read(Path(collection.output) / "collection-receipt.json")
    assert calls == list(range(48)) and receipt["all_planned_slots"][0]["status"] == "execution_failed"
    assert receipt["corrective_reruns"] == 0


def test_readiness_boolean_alone_cannot_authorize_freeze(args, tmp_path):
    path = tmp_path / "readiness.json"
    r.write_new(path, {"passed": True})
    with pytest.raises(ValueError, match="not bound"):
        r.verify_readiness(path, args)


def test_bound_readiness_directory_detects_added_and_changed_files(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "raw.json").write_text("{}")
    record = r.bind_evidence(root)
    r.verify_evidence(record)
    (root / "extra.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory"):
        r.verify_evidence(record)
