"""Synthetic runner/checkpoint integration: no server, GPU or model execution."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.kaggle_limbo import run, runtime
from research.kaggle_limbo.checkpoint import CheckpointStore, SessionBudget, load


@pytest.fixture
def runner_fixture(tmp_path, monkeypatch):
    clock = [100.0]
    study, runtime_dir = tmp_path / "study", tmp_path / "runtime"
    study.mkdir()
    runtime_dir.mkdir()
    runtime.save(study / "bundle-manifest.json", {"engineering_fixture_only": True})
    condition = {"synthetic_gpu_condition": "not-hardware-evidence"}
    devices = [{"uuid": "invented-gpu", "name": "invented"}]
    setup = {"condition": condition, "gpu_devices": devices, "server": {"pid": 123}}
    runtime.save(runtime_dir / "setup.json", setup)
    schedule = [{"slot": number, "model_id": "synthetic-model", "arm": "guard"}
                for number in range(3456)]
    model = {"id": "synthetic-model", "family": "synthetic"}
    protocol = {"schedule": schedule, "models": [model], "counts": {"planned_slots": 3456},
                "limits": {"episode_timeout_s": 1800, "request_timeout_s": 300}}
    lineage = {"protocol": "synthetic-3456-slot-plan", "condition": condition}
    calls, loads, unloads = [], [], []
    monkeypatch.setenv("CONSEQAX_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("CONSEQAX_SESSION_START_MONOTONIC", "100.0")
    monkeypatch.setattr(runtime, "gpu_inventory", lambda: devices)
    monkeypatch.setattr(runtime, "condition", lambda values: condition)
    monkeypatch.setattr(run, "make_lineage", lambda *args: (lineage, protocol))
    monkeypatch.setattr(run.time, "monotonic", lambda: clock[0])

    def budget(**kwargs):
        return SessionBudget(**kwargs, clock=lambda: clock[0])

    monkeypatch.setattr(run, "SessionBudget", budget)
    monkeypatch.setattr(run, "preflight", lambda *args: {"synthetic-model": {"sha256": "a" * 64, "bytes": 1}})

    def load_model(server, selected, path):
        Path(path).mkdir(parents=True)
        runtime.save(Path(path) / "gpu-load-proof.json", {"synthetic_load_proof": True})
        loads.append(selected["id"])
        return SimpleNamespace(model=selected["id"])

    monkeypatch.setattr(runtime, "load_model", load_model)
    monkeypatch.setattr(runtime, "unload", lambda: unloads.append("unload"))
    from research.kaggle_limbo import audit
    monkeypatch.setattr(audit, "audit_kaggle_episode", lambda directory, slot, **kwargs: {
        "passed": True, "grade_available": True, "normal_execution_return": True,
        "native_grade": {"TS": True, "EOS": True}, "synthetic_fixture": True})
    return SimpleNamespace(clock=clock, study=study, lineage=lineage, protocol=protocol,
                           calls=calls, loads=loads, unloads=unloads, root=tmp_path)


def test_collect_preserves_completed_interrupted_and_unstarted_on_export_reimport(runner_fixture, monkeypatch):
    fixture = runner_fixture
    first = fixture.root / "session-one/state"

    def fake_episode(study, episode, slot, lineage, lease, devices, timeout, **kwargs):
        fixture.calls.append(slot["slot"])
        assert timeout == 1800
        fixture.clock[0] += 10801
        if slot["slot"] == 0:
            runtime.save(episode / "native-result.json", {"synthetic_fixture": True})
            return "returned"
        (episode / "partial.jsonl").write_bytes(b'{"actual_result":"unknown-fixture"}\n')
        return "interrupted"

    monkeypatch.setattr(run, "execute_episode", fake_episode)
    run.collect(fixture.study, first)
    assert fixture.calls == [0, 1]
    assert fixture.loads == ["synthetic-model"]
    snapshot = first.parent / "checkpoint.zip"
    assert snapshot.is_file()
    with CheckpointStore(first, fixture.lineage, fixture.protocol["schedule"]) as store:
        assert store.snapshot()["statuses"]["completed"] == 1
        assert store.snapshot()["statuses"]["interrupted"] == 1
        assert store.snapshot()["unstarted"] == 3454
        assert store.next_unstarted()["slot"] == 2
    progress = load(first.parent / "progress.json")
    group = progress["groups"]["synthetic-model / guard"]
    assert group["planned"] == 3456 and group["graded"] == 1 and group["unavailable"] == 3455
    fixture.calls.clear()
    fixture.clock[0] = 50000
    monkeypatch.setenv("CONSEQAX_SESSION_START_MONOTONIC", "50000")

    def one_more(study, episode, slot, lineage, lease, devices, timeout, **kwargs):
        fixture.calls.append(slot["slot"])
        fixture.clock[0] += 30000
        runtime.save(episode / "native-result.json", {"synthetic_fixture": True})
        return "returned"

    monkeypatch.setattr(run, "execute_episode", one_more)
    second = fixture.root / "session-two/state"
    run.collect(fixture.study, second, resume_from=snapshot)
    assert fixture.calls == [2]
    with CheckpointStore(second, fixture.lineage, fixture.protocol["schedule"]) as store:
        assert store.snapshot()["statuses"]["completed"] == 2
        assert store.snapshot()["statuses"]["interrupted"] == 1
        assert store.next_unstarted()["slot"] == 3


def test_setup_time_exhaustion_starts_zero_slots_and_exports_even_if_unload_fails(runner_fixture, monkeypatch):
    fixture = runner_fixture
    fixture.clock[0] = 100 + 7 * 3600
    output = fixture.root / "exhausted/state"

    def never(*args, **kwargs):
        pytest.fail("Setup-exhausted session must not start preflight or measured inference")

    monkeypatch.setattr(run, "preflight", never)
    monkeypatch.setattr(run, "execute_episode", never)
    monkeypatch.setattr(runtime, "unload", lambda: (_ for _ in ()).throw(RuntimeError("fixture unload failure")))
    run.collect(fixture.study, output)
    assert (output.parent / "checkpoint.zip").is_file()
    with CheckpointStore(output, fixture.lineage, fixture.protocol["schedule"]) as store:
        assert store.snapshot()["started"] == 0
        assert store.snapshot()["unstarted"] == 3456


def test_failed_preflight_exports_without_spending_measured_slots(runner_fixture, monkeypatch):
    fixture = runner_fixture
    output = fixture.root / "failed-preflight/state"

    def fail(*args):
        raise RuntimeError("synthetic GPU qualification failure")

    monkeypatch.setattr(run, "preflight", fail)
    with pytest.raises(RuntimeError, match="qualification failure"):
        run.collect(fixture.study, output)
    assert (output.parent / "checkpoint.zip").is_file()
    with CheckpointStore(output, fixture.lineage, fixture.protocol["schedule"]) as store:
        assert store.snapshot()["started"] == 0


def test_execute_episode_kills_entire_process_group_on_timeout_and_seals_prefix(tmp_path, monkeypatch):
    @dataclass
    class FixtureLease:
        model: str = "synthetic-model"

    study, output = tmp_path / "study", tmp_path / "slot/episode"
    study.mkdir()
    output.mkdir(parents=True)
    observed = {"killed": False, "options": None}

    class Child:
        pid = 424242

        def wait(self, timeout):
            if not observed["killed"]:
                raise run.subprocess.TimeoutExpired("synthetic child", timeout)
            return -9

        def poll(self):
            return -9 if observed["killed"] else None

    def launch(command, **kwargs):
        observed["options"] = kwargs
        return Child()

    def kill_group(pid, sig):
        assert pid == Child.pid
        assert sig == run.signal.SIGKILL
        observed["killed"] = True

    monkeypatch.setattr(run.subprocess, "Popen", launch)
    monkeypatch.setattr(run.os, "killpg", kill_group, raising=False)
    # SIGKILL is absent on Windows, but the real collector is Linux only.
    monkeypatch.setattr(run.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setenv("SYNTHETIC_API_KEY", "fixture-not-a-credential")
    status = run.execute_episode(study, output, {"slot": 0}, {"condition": {}}, FixtureLease(), [], 1800)
    assert status == "interrupted" and observed["killed"]
    assert observed["options"]["start_new_session"] is True
    assert "SYNTHETIC_API_KEY" not in observed["options"]["env"]
    assert load(output / "parent-terminal.json")["no_automatic_retry"] is True
    assert "parent-terminal.json" in load(output / "manifest.json")


def test_worker_rejects_changed_static_lineage_before_model_or_task_construction(tmp_path, monkeypatch):
    config = tmp_path / "worker.json"
    config.write_text(json.dumps({"study_dir": "synthetic-study", "output": "unused",
        "condition": {}, "lineage": {"protocol": "wrong"}}), encoding="utf-8")
    monkeypatch.setattr(run, "make_lineage", lambda *args: ({"protocol": "frozen"}, {}))
    with pytest.raises(ValueError, match="Worker lineage changed"):
        run.run_worker(config)
