"""Synthetic process leases; no model, network or real-process observation."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from scripts import observe_native_resources as observer


class MissingProcess(Exception):
    pass


class FakeProcess:
    def __init__(self, pid, path, created, parent):
        self.pid, self.path, self.created, self.parent = pid, str(path), created, parent
        self.running, self.cpu, self.rss, self.thread_count = True, 5.0, 120, 4

    def create_time(self):
        return self.created

    def exe(self):
        return self.path

    def ppid(self):
        return self.parent

    def is_running(self):
        return self.running

    def oneshot(self):
        return nullcontext()

    def memory_info(self):
        return SimpleNamespace(rss=self.rss, vms=240)

    def cpu_times(self):
        return SimpleNamespace(user=self.cpu, system=2.0)

    def num_threads(self):
        return self.thread_count

    def status(self):
        return "running"


@pytest.fixture
def bound(tmp_path):
    server, runner = tmp_path / "server.exe", tmp_path / "runner.exe"
    server.write_bytes(b"synthetic server")
    runner.write_bytes(b"synthetic runner")
    stamp = datetime(2026, 10, 21, tzinfo=timezone.utc).timestamp()
    processes = {10: FakeProcess(10, server, stamp, 1),
                 20: FakeProcess(20, runner, stamp + 5, 10)}
    seen = []

    def process(pid):
        seen.append(pid)
        if pid not in processes:
            raise MissingProcess("synthetic missing PID")
        return processes[pid]

    psutil = SimpleNamespace(Process=process, NoSuchProcess=MissingProcess,
                             ZombieProcess=MissingProcess,
                             virtual_memory=lambda: SimpleNamespace(total=1000, available=600))
    launch = tmp_path / "launch.json"
    launch.write_text(json.dumps({"server_pid": 10, "server_executable": str(server),
                                 "server_executable_sha256": observer.sha_file(server),
                                 "started_utc": datetime.fromtimestamp(stamp - .5, timezone.utc).isoformat(),
                                 "finished_utc": datetime.fromtimestamp(stamp + .5, timezone.utc).isoformat()}))
    render = tmp_path / "render.json"
    render.write_text(json.dumps({"passed": True, "tokenizer_runner_binding": {
        "pid": 20, "executable": str(runner), "executable_sha256": observer.sha_file(runner),
        "model_blob_sha256": "a" * 64},
        "started_utc": datetime.fromtimestamp(stamp + 4, timezone.utc).isoformat(),
        "finished_utc": datetime.fromtimestamp(stamp + 6, timezone.utc).isoformat()}))
    binding = observer.prepare_binding(launch, render, psutil)
    return SimpleNamespace(binding=binding, psutil=psutil, processes=processes,
                           seen=seen, launch=launch, render=render, path=tmp_path)


def test_bind_exact_creation_identity_and_only_requested_pids(bound):
    assert set(bound.seen) == {10, 20}
    assert bound.binding["processes"]["runner"]["parent_pid"] == 10
    assert bound.binding["inputs"]["launch"]["sha256"] == observer.sha_file(bound.launch)
    assert bound.binding["script"]["sha256"] == observer.sha_file(observer.__file__)


@pytest.mark.parametrize("pid", [True, 0, -1, "10", 10.0])
def test_reject_ambiguous_pid(pid):
    with pytest.raises(ValueError):
        observer.positive_pid(pid)


@pytest.mark.parametrize("change", ["pid_reuse", "parent", "exit", "exe", "file"])
def test_lease_changes_refused(bound, change):
    process = bound.processes[20]
    if change == "pid_reuse":
        process.created += 100
    elif change == "parent":
        process.parent = 999
    elif change == "exit":
        process.running = False
    elif change == "exe":
        process.path = str(bound.path / "other.exe")
    else:
        (bound.path / "runner.exe").write_bytes(b"different executable bytes")
    with pytest.raises(observer.LeaseChanged):
        observer.sample_resources(bound.binding, bound.psutil, 0)


def test_startup_pid_reuse_and_failed_render_refused(bound):
    bound.processes[10].created += 100
    with pytest.raises(observer.LeaseChanged, match="creation time"):
        observer.prepare_binding(bound.launch, bound.render, bound.psutil)
    render = json.loads(bound.render.read_text())
    render["passed"] = False
    bound.render.write_text(json.dumps(render))
    with pytest.raises(ValueError, match="passed render"):
        observer.prepare_binding(bound.launch, bound.render, bound.psutil)


def test_sample_counter_rates_and_system_ram(bound):
    first = observer.sample_resources(bound.binding, bound.psutil, 0)
    assert first["processes"]["runner"]["cpu_percent_over_interval"] is None
    bound.processes[20].cpu += 45
    second = observer.sample_resources(bound.binding, bound.psutil, 30, first)
    assert second["processes"]["runner"]["cpu_percent_over_interval"] == 150
    assert second["system_ram"] == {"total_bytes": 1000, "available_bytes": 600}
    assert set(bound.seen) == {10, 20}
    backwards = deepcopy(second)
    backwards["processes"]["runner"]["cpu_user_seconds"] += 1
    with pytest.raises(observer.LeaseChanged, match="counters"):
        observer.sample_resources(bound.binding, bound.psutil, 60, backwards)


def test_stop_flushes_stream_and_seals_complete_artifacts(bound):
    stop_file, output = bound.path / "STOP", bound.path / "observation"
    clock = [0]

    def sleep(seconds):
        # The first sample must already be visible before this stop request.
        rows = (output / "resources.jsonl").read_text().splitlines()
        assert len(rows) == 1 and json.loads(rows[0])["sample_index"] == 0
        clock[0] += seconds
        stop_file.touch()

    code, summary = observer.observe(bound.binding, output, stop_file, 30, bound.psutil,
                                     monotonic=lambda: clock[0], sleep=sleep)
    assert code == 0 and summary["terminal_reason"] == "explicit_stop_file"
    assert summary["samples"] == 1
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["complete"] is True
    assert set(manifest["files"]) == {p.name for p in output.iterdir() if p.name != "manifest.json"}
    for name, digest in manifest["files"].items():
        assert observer.sha_file(output / name) == digest
    with pytest.raises(FileExistsError):
        observer.observe(bound.binding, output, stop_file, 30, bound.psutil)


def test_bound_lease_failure_retains_prefix_and_terminal_reason(bound):
    stop_file, output = bound.path / "STOP", bound.path / "failed-observation"
    clock = [0]

    def sleep(seconds):
        clock[0] += seconds
        bound.processes[20].created += 1

    code, summary = observer.observe(bound.binding, output, stop_file, 2, bound.psutil,
                                     monotonic=lambda: clock[0], sleep=sleep)
    assert code == 2 and summary["terminal_reason"] == "bound_lease_changed"
    assert summary["samples"] == 1
    assert len((output / "resources.jsonl").read_text().splitlines()) == 1
    assert (output / "manifest.json").is_file()


def test_changed_binding_or_signal_never_creates_resource_sample(bound):
    bound.launch.write_text("changed launch")
    output = bound.path / "changed-input"
    code, summary = observer.observe(bound.binding, output, bound.path / "STOP", 30, bound.psutil)
    assert code == 2 and summary["samples"] == 0
    signal_output = bound.path / "signal-input"
    code, summary = observer.observe(bound.binding, signal_output, bound.path / "STOP", 30,
                                     bound.psutil, stop_requested=lambda: "signal_2")
    assert code == 130 and summary["terminal_reason"] == "signal_2"
    assert summary["samples"] == 0


@pytest.mark.parametrize("interval", [0, -1, float("inf"), float("nan")])
def test_invalid_interval_creates_nothing(bound, interval):
    output = bound.path / "invalid"
    with pytest.raises(ValueError):
        observer.observe(bound.binding, output, bound.path / "STOP", interval, bound.psutil)
    assert not output.exists()
