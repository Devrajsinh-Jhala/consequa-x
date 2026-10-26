"""Invented GPU proofs and cached responses; zero live GPU/model generations.

The native task/world/grade replay is real local code. The GPU diagnostics are
explicit synthetic fixtures that test rejection logic, not observed hardware.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.expanded_limbo import audit as physical_audit  # noqa: E402
from research.kaggle_limbo import audit as gpu_audit  # noqa: E402
from test_expanded_limbo_audit import (  # noqa: E402
    exact_sdk as _exact_sdk, invented_episode as _invented_episode, seal, write,
)

exact_sdk = _exact_sdk
invented_episode = _invented_episode


def condition():
    return {"runtime_version": "0.40.10", "archive_sha256": gpu_audit.ARCHIVE_SHA256,
            "gpu_name": "Invented synthetic GPU", "compute_capability": "8.0",
            "driver_version": "invented-driver", "python_version": "3.12.fixture",
            "library_versions": {"psutil": "fixture-only"}}


def layer_proof(runtime):
    line = "load_tensors: offloaded 29/29 layers to GPU"
    return {"schema": "conseqax-gpu-layer-offload-v1", "runner_pid": runtime["runner_pid"],
            "runner_create_time": runtime["runner_create_time"],
            "model_blob_sha256": runtime["model_blob_sha256"], "requested_gpu_layers": 999,
            "offloaded_layers": 29, "total_layers": 29, "log_line": line,
            "log_line_sha256": hashlib.sha256(line.encode()).hexdigest()}


def prepare_gpu_fixture(directory):
    """Add deliberately invented hardware proofs to a real cached native replay."""
    model = directory / "model"
    config = physical_audit.load(model / "expanded-client-config.json")
    runtime = {**config["runtime"], "api_base": "http://127.0.0.1:11436/v1",
        "model_blob": "/kaggle/working/invented-model.gguf", "model_blob_sha256": "a" * 64,
        "server_executable": "/kaggle/working/runtime/bin/ollama",
        "runner_executable": "/kaggle/working/runtime/lib/ollama/llama-server",
        "server_executable_sha256": "b" * 64, "runner_executable_sha256": "c" * 64,
        "server_pid": 101, "runner_pid": 102, "server_create_time": 1000.0,
        "runner_create_time": 1001.0, "runner_port": 31337, "parallel_slots": 1}
    config["runtime"] = runtime
    write(model / "expanded-client-config.json", config)
    for path in model.glob("*-context.json"):
        proof = physical_audit.load(path)
        proof["runtime_binding"] = runtime
        proof["resident_response"]["models"][0].update(size=10_000, size_vram=10_000)
        write(path, proof)
    lineage = {"condition": condition()}
    write(model / "kaggle-gpu-config.json", {"schema": gpu_audit.CONDITION_SCHEMA,
        "condition": lineage["condition"], "runtime": runtime,
        "cpu_fallback_allowed": False,
        "gpu_load_proof": layer_proof(runtime),
        "gpu_devices": [{"name": "Invented synthetic GPU", "uuid": "GPU-fixture-no-hardware",
                         "compute_capability": "8.0", "driver_version": "invented-driver"}]})
    seal(directory)
    limits = {"max_requests": 16, "max_output_tokens": 512, "work": dict(physical_audit.DEFAULT_WORK)}
    model_binding = {"id": runtime["model"], "context_tokens": 8192,
                     "weights": {"sha256": "a" * 64, "bytes": 1}}
    return lineage, limits, model_binding


def run_audit(directory, slot, parameters):
    lineage, limits, model = parameters
    return gpu_audit.audit_kaggle_episode(directory, slot, lineage=lineage,
        expected_limits=limits, expected_model=model)


def test_real_native_cached_world_replay_under_explicit_synthetic_gpu_condition(invented_episode):
    directory, slot = invented_episode
    parameters = prepare_gpu_fixture(directory)
    result = run_audit(directory, slot, parameters)
    assert result["passed"] and result["grade_available"]
    assert result["gpu_context_proofs"] == result["model_dispatches"] == 3
    assert result["scope"]["separate_kaggle_gpu_condition"]
    assert result["scope"]["saved_gpu_residency_proof_consistency"]
    assert result["scope"]["fresh_gpu_inference_during_audit"] is False
    assert result["scope"]["independently_authenticated_gpu_hardware"] is False
    assert result["scope"]["pooled_with_historical_cpu_cohort"] is False


@pytest.mark.parametrize("wrong", ["protocol_condition", "protocol_budget", "protocol_weights",
                                    "runtime_lease", "archive", "windows_path"])
def test_gpu_native_replay_rejects_wrong_frozen_condition(invented_episode, wrong):
    directory, slot = invented_episode
    lineage, limits, model = prepare_gpu_fixture(directory)
    if wrong == "protocol_condition":
        lineage["condition"]["driver_version"] = "another-driver"
    elif wrong == "protocol_budget":
        limits["max_requests"] = 17
    elif wrong == "protocol_weights":
        model["weights"]["sha256"] = "d" * 64
    else:
        path = directory / "model/kaggle-gpu-config.json"
        value = physical_audit.load(path)
        if wrong == "runtime_lease":
            value["runtime"]["runner_pid"] += 1
        elif wrong == "archive":
            lineage["condition"]["archive_sha256"] = value["condition"]["archive_sha256"] = "f" * 64
        else:
            value["runtime"]["server_executable"] = "C:/invented/ollama.exe"
            expanded = physical_audit.load(directory / "model/expanded-client-config.json")
            expanded["runtime"] = value["runtime"]
            write(directory / "model/expanded-client-config.json", expanded)
        write(path, value)
        seal(directory)
    with pytest.raises(ValueError):
        run_audit(directory, slot, (lineage, limits, model))


@pytest.mark.parametrize("vram", [0, -1, True])
def test_every_dispatched_context_rejects_zero_or_noninteger_gpu_memory(invented_episode, vram):
    directory, slot = invented_episode
    parameters = prepare_gpu_fixture(directory)
    path = directory / "model/0002-context.json"
    value = physical_audit.load(path)
    value["resident_response"]["models"][0]["size_vram"] = vram
    write(path, value)
    seal(directory)
    with pytest.raises(ValueError, match="GPU|CPU"):
        run_audit(directory, slot, parameters)


def test_positive_gpu_memory_allows_cpu_host_buffers_without_percentage_proxy():
    runtime = {"model": "fixture", "model_digest": "a" * 64, "context_tokens": 8192}
    proof = {"runtime_binding": runtime, "resident_response": {"models": [{
        "name": "fixture", "digest": "a" * 64, "context_length": 8192,
        "size": 100, "size_vram": 50}]}}
    assert gpu_audit.verify_gpu_residency(proof, runtime)["size_vram"] == 50
    proof["resident_response"]["models"][0]["size_vram"] = 0
    with pytest.raises(ValueError, match="positive integer"):
        gpu_audit.verify_gpu_residency(proof, runtime)


@pytest.mark.parametrize("tamper", ["partial", "zero", "pid", "birth", "weights", "request", "line", "hash"])
def test_full_layer_offload_proof_rejects_partial_or_unbound_evidence(invented_episode, tamper):
    directory, slot = invented_episode
    parameters = prepare_gpu_fixture(directory)
    path = directory / "model/kaggle-gpu-config.json"
    config = physical_audit.load(path)
    proof = config["gpu_load_proof"]
    if tamper == "partial":
        proof["offloaded_layers"] = 28
        proof["log_line"] = "load_tensors: offloaded 28/29 layers to GPU"
        proof["log_line_sha256"] = hashlib.sha256(proof["log_line"].encode()).hexdigest()
    elif tamper == "zero":
        proof["offloaded_layers"] = proof["total_layers"] = 0
    elif tamper == "pid":
        proof["runner_pid"] += 1
    elif tamper == "birth":
        proof["runner_create_time"] += 1
    elif tamper == "weights":
        proof["model_blob_sha256"] = "d" * 64
    elif tamper == "request":
        proof["requested_gpu_layers"] = 28
    elif tamper == "line":
        proof["log_line"] = "load_tensors: no authoritative offload count"
        proof["log_line_sha256"] = hashlib.sha256(proof["log_line"].encode()).hexdigest()
    else:
        proof["log_line_sha256"] = "d" * 64
    write(path, config)
    seal(directory)
    with pytest.raises(ValueError, match="GPU"):
        run_audit(directory, slot, parameters)


def test_gpu_label_cannot_hide_resealed_native_grade_tampering(invented_episode):
    directory, slot = invented_episode
    parameters = prepare_gpu_fixture(directory)
    path = directory / "native-result.json"
    value = physical_audit.load(path)
    value["grade"]["EOS"] = not value["grade"]["EOS"]
    write(path, value)
    seal(directory)
    with pytest.raises(ValueError, match="grade differs"):
        run_audit(directory, slot, parameters)


def test_historical_cpu_artifact_cannot_be_relabelled_gpu(invented_episode):
    directory, slot = invented_episode
    _, limits, model = prepare_gpu_fixture(directory)
    (directory / "model/kaggle-gpu-config.json").unlink()
    seal(directory)
    with pytest.raises(FileNotFoundError):
        gpu_audit.audit_kaggle_episode(directory, slot, lineage={"condition": condition()},
                                      expected_limits=limits, expected_model=model)


def test_static_gpu_condition_excludes_ephemeral_uuid():
    value = condition()
    gpu_audit.validate_condition(value)
    changed = copy.deepcopy(value)
    changed["gpu_uuid"] = "an-ephemeral-device"
    with pytest.raises(ValueError, match="inventory"):
        gpu_audit.validate_condition(changed)


def test_gpu_instance_uuid_can_change_but_device_class_must_match(invented_episode):
    directory, slot = invented_episode
    parameters = prepare_gpu_fixture(directory)
    path = directory / "model/kaggle-gpu-config.json"
    value = physical_audit.load(path)
    value["gpu_devices"][0]["uuid"] = "another-invented-instance-of-same-class"
    write(path, value)
    seal(directory)
    assert run_audit(directory, slot, parameters)["passed"]
    value["gpu_devices"][0]["compute_capability"] = "another-class"
    write(path, value)
    seal(directory)
    with pytest.raises(ValueError, match="diagnostic device differs"):
        run_audit(directory, slot, parameters)


def test_gpu_auditor_imports_no_gpu_runner_or_windows_setup():
    source = (ROOT / "research/kaggle_limbo/audit.py").read_text(encoding="utf-8")
    assert "from .runtime" not in source
    assert "from .transport" not in source
    assert "import torch" not in source
    assert "from research.expanded_limbo.runtime" not in source


def test_sealed_native_gpu_evidence_survives_export_and_interrupted_continuation(invented_episode, tmp_path):
    from research.kaggle_limbo.checkpoint import CheckpointStore

    episode, slot = invented_episode
    parameters = prepare_gpu_fixture(episode)
    lineage = {**parameters[0], "protocol_sha256": "7" * 64}
    schedule = [{**slot, "slot": number} for number in range(3)]
    first = tmp_path.with_name(tmp_path.name + "-first-checkpoint")
    resumed = tmp_path.with_name(tmp_path.name + "-resumed-checkpoint")
    snapshot = tmp_path.with_name(tmp_path.name + "-preserved.zip")
    with CheckpointStore(first, lineage, schedule) as store:
        store.begin_session("session-a", {"gpu_uuid": "invented-instance-a"})
        store.reserve(0, "session-a")
        store.finish(0, "completed", episode)
        store.export(snapshot)
    with CheckpointStore(resumed, lineage, schedule) as store:
        store.import_snapshot(snapshot)
        assert store.next_unstarted()["slot"] == 1
        copied = store.slot_directory(0)
        assert run_audit(copied, slot, parameters)["passed"]
        store.begin_session("session-b", {"gpu_uuid": "invented-instance-b"})
        store.reserve(1, "session-b")
        prefix = store.slot_directory(1) / "retained-prefix.jsonl"
        prefix.write_bytes(b'{"event":"generation-dispatched-result-unknown"}\n')
        assert store.next_unstarted()["slot"] == 2
        # Simulate a dead notebook without creating a terminal or retry.
    with CheckpointStore(resumed, lineage, schedule) as store:
        store.reconcile_orphans("session-c")
        assert store.terminals[1]["status"] == "interrupted"
        assert prefix.read_bytes().endswith(b"\n")
        assert store.next_unstarted()["slot"] == 2
        with pytest.raises(ValueError, match="cannot repeat"):
            store.reserve(1, "session-c")
        assert store.snapshot()["statuses"]["completed"] == 1
        assert store.snapshot()["statuses"]["interrupted"] == 1
    # A new process cannot smuggle a new protocol into the same evidence tree.
    changed = {**lineage, "protocol_sha256": "8" * 64}
    with pytest.raises(ValueError, match="lineage differs"):
        CheckpointStore(resumed, changed, schedule)


def test_checkpoint_refuses_corruption_of_sealed_native_evidence(invented_episode, tmp_path):
    from research.kaggle_limbo.checkpoint import CheckpointStore

    episode, slot = invented_episode
    parameters = prepare_gpu_fixture(episode)
    destination = tmp_path.with_name(tmp_path.name + "-checkpoint-corruption")
    with CheckpointStore(destination, parameters[0], [slot]) as store:
        store.begin_session("synthetic-session", {"gpu_uuid": "fixture-only"})
        store.reserve(0, "synthetic-session")
        store.finish(0, "completed", episode)
        native = store.slot_directory(0) / "native-result.json"
    value = physical_audit.load(native)
    value["grade"]["TS"] = not value["grade"]["TS"]
    write(native, value)
    with pytest.raises(ValueError, match="Sealed episode"):
        CheckpointStore(destination, parameters[0], [slot])


def test_eight_hour_cutoff_preserves_full_episode_budget_before_reservation(tmp_path):
    from research.kaggle_limbo.checkpoint import CheckpointStore, SessionBudget

    now = [0.0]
    budget = SessionBudget(seconds=8 * 3600, flush_margin=1800, episode_allowance=7200,
                           clock=lambda: now[0])
    now[0] = 8 * 3600 - 9000
    assert budget.can_start_next()
    now[0] += 0.001
    assert not budget.can_start_next()
    with CheckpointStore(tmp_path / "cutoff", {"protocol": "synthetic"}, [{"slot": 0}]) as store:
        store.begin_session("budget-session", {})
        with pytest.raises(ValueError, match="Session cutoff"):
            store.reserve(0, "budget-session", budget=budget)
        assert store.snapshot()["started"] == 0
        assert store.next_unstarted()["slot"] == 0


def test_checkpoint_rejects_divergent_session_forks(tmp_path):
    from research.kaggle_limbo.checkpoint import CheckpointStore

    lineage, schedule = {"protocol": "same-synthetic-protocol"}, [{"slot": 0}]
    ancestor, fork = tmp_path / "ancestor.zip", tmp_path / "fork.zip"
    with CheckpointStore(tmp_path / "root", lineage, schedule) as root:
        root.begin_session("ancestor-session", {})
        root.export(ancestor)
    with CheckpointStore(tmp_path / "branch-a", lineage, schedule) as left:
        left.import_snapshot(ancestor)
        left.begin_session("left-session", {})
        with CheckpointStore(tmp_path / "branch-b", lineage, schedule) as right:
            right.import_snapshot(ancestor)
            right.begin_session("right-session", {})
            right.export(fork)
        with pytest.raises(ValueError, match="history fork"):
            left.import_snapshot(fork)


@pytest.mark.parametrize("vram", [100, 50, 1, 0])
def test_gpu_transport_identity_gate_uses_actual_bound_file_hashes_and_residency(tmp_path, monkeypatch, vram):
    """Mock process/API observations; hash real fixture files; generate nothing."""
    from research.kaggle_limbo.transport import KaggleGPUClient
    from research.limbo_agent.transport import file_sha256
    from research.kaggle_limbo import transport

    files = [tmp_path / name for name in ("ollama", "llama-server", "invented.gguf")]
    for number, path in enumerate(files):
        path.write_bytes(b"invented runtime file " + bytes([number]))
    binding = SimpleNamespace(server_pid=101, runner_pid=102,
        server_executable=str(files[0]), runner_executable=str(files[1]), model_blob=str(files[2]),
        server_executable_sha256=file_sha256(files[0]),
        runner_executable_sha256=file_sha256(files[1]), model_blob_sha256=file_sha256(files[2]),
        server_create_time=1000.0, runner_create_time=1001.0, runner_port=31337,
        context_tokens=8192, api_base="http://127.0.0.1:11436/v1", model="fixture",
        model_digest="a" * 64)
    command = [str(files[1]), "--model", str(files[2]), "--port", "31337", "--host", "127.0.0.1",
               "-np", "1", "-c", "8192", "-ngl", "999", "--offline"]

    def process(pid):
        number = 0 if pid == 101 else 1
        return SimpleNamespace(exe=lambda: str(files[number]),
            create_time=lambda: 1000.0 + number, cmdline=lambda: list(command))

    monkeypatch.setattr(transport.psutil, "Process", process)
    client = KaggleGPUClient.__new__(KaggleGPUClient)
    client.binding, client.condition, client._identity_files = binding, condition(), {}
    client.gpu_load_proof = layer_proof(vars(binding))

    def provider(method, url, payload=None):
        if url.endswith("/api/version"):
            return {"version": "0.40.10"}
        return {"models": [{"name": "fixture", "digest": "a" * 64,
            "context_length": 8192, "size": 100, "size_vram": vram}]}

    client._json_call = provider
    if vram > 0:
        client._verify_identity(initial=True)
        files[2].write_bytes(b"changed after successful preflight")
        with pytest.raises(RuntimeError, match="changed after preflight"):
            client._verify_identity()
    else:
        with pytest.raises(RuntimeError, match="CPU fallback"):
            client._verify_identity(initial=True)
