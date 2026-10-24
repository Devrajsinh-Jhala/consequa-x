"""Read-only resource observations of two bound research processes.

This auxiliary observer never imports the benchmark, calls a model or a server,
enumerates unrelated processes, changes environment settings, or stops a process.
The default period is 30 seconds. Touch the explicit --stop-file to finish and
seal the output; an abrupt interruption leaves its already-flushed JSONL prefix.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time


class LeaseChanged(RuntimeError):
    """A bound PID, creation time, executable, or parent no longer matches."""


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def normalized_path(value):
    return os.path.normcase(os.path.abspath(value))


def positive_pid(value):
    if type(value) is not int or value < 1:
        raise ValueError("Process identities require positive integer PIDs")
    return value


def creation_window(record):
    start = datetime.fromisoformat(record["started_utc"])
    finish = datetime.fromisoformat(record["finished_utc"])
    if start.tzinfo is None or finish.tzinfo is None or finish < start:
        raise ValueError("Bound startup records require ordered timezone-aware times")
    return start.timestamp() - 1, finish.timestamp() + 1


def bind_process(psutil_module, pid, executable, expected_sha256, window, expected_parent=None):
    """Read only this PID and authenticate its executable and original start."""
    process = psutil_module.Process(positive_pid(pid))
    created = process.create_time()
    actual_executable = process.exe()
    parent = process.ppid()
    if not window[0] <= created <= window[1]:
        raise LeaseChanged("Process creation time falls outside its bound startup record")
    if normalized_path(actual_executable) != normalized_path(executable):
        raise LeaseChanged("Bound process executable path changed")
    if expected_parent is not None and parent != expected_parent:
        raise LeaseChanged("Bound runner is not a child of the research server")
    actual_sha = sha_file(actual_executable)
    if actual_sha != expected_sha256:
        raise LeaseChanged("Bound executable bytes changed")
    if not process.is_running() or process.create_time() != created:
        raise LeaseChanged("Bound process changed while its identity was read")
    stat = Path(actual_executable).stat()
    return {
        "pid": pid, "create_time_epoch_seconds": created,
        "create_time_utc": datetime.fromtimestamp(created, timezone.utc).isoformat(),
        "executable": actual_executable, "executable_sha256": actual_sha,
        "executable_size": stat.st_size, "executable_mtime_ns": stat.st_mtime_ns,
        "parent_pid": parent,
    }


def prepare_binding(launch_path, render_path, psutil_module):
    launch_path, render_path = Path(launch_path).resolve(), Path(render_path).resolve()
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    render = json.loads(render_path.read_text(encoding="utf-8"))
    if render.get("passed") is not True:
        raise ValueError("A passed render binding is required")
    server_pid = positive_pid(launch["server_pid"])
    runner = render["tokenizer_runner_binding"]
    processes = {
        "server": bind_process(psutil_module, server_pid, launch["server_executable"],
                               launch["server_executable_sha256"], creation_window(launch)),
        "runner": bind_process(psutil_module, runner["pid"], runner["executable"],
                               runner["executable_sha256"], creation_window(render), server_pid),
    }
    return {
        "schema": "native-resource-observer-binding-v1", "created_utc": utc(),
        "scope": "Read-only measurements of the two bound research processes and system RAM",
        "script": {"path": str(Path(__file__).resolve()), "sha256": sha_file(__file__)},
        "inputs": {
            "launch": {"path": str(launch_path), "sha256": sha_file(launch_path)},
            "render": {"path": str(render_path), "sha256": sha_file(render_path)},
        },
        "processes": processes,
        "model_blob_sha256": runner["model_blob_sha256"],
        "cpu_percent_definition": "100 * process CPU user+system seconds delta / monotonic wall seconds delta; may exceed 100 across CPU cores; first sample null",
        "limitations": ["30-second samples do not establish the true peak between samples",
                        "RSS is a process working set; shared pages may appear in both processes",
                        "System available RAM includes effects of unobserved applications",
                        "No inference about task success or model configuration is made"],
        "actual_generation_requests": 0, "network_requests": 0,
    }


def checked_process(psutil_module, identity):
    process = psutil_module.Process(identity["pid"])
    if (process.create_time() != identity["create_time_epoch_seconds"]
            or normalized_path(process.exe()) != normalized_path(identity["executable"])
            or process.ppid() != identity["parent_pid"]
            or not process.is_running()):
        raise LeaseChanged("Bound process identity changed or stopped")
    stat = Path(identity["executable"]).stat()
    if (stat.st_size != identity["executable_size"]
            or stat.st_mtime_ns != identity["executable_mtime_ns"]):
        raise LeaseChanged("Bound executable file metadata changed")
    return process


def sample_resources(binding, psutil_module, elapsed_seconds, previous=None):
    rows = {}
    for name, identity in binding["processes"].items():
        process = checked_process(psutil_module, identity)
        with process.oneshot():
            memory = process.memory_info()
            cpu = process.cpu_times()
            rows[name] = {
                "pid": identity["pid"], "create_time_epoch_seconds": process.create_time(),
                "rss_bytes": int(memory.rss), "vms_bytes": int(memory.vms),
                "cpu_user_seconds": float(cpu.user), "cpu_system_seconds": float(cpu.system),
                "threads": int(process.num_threads()), "status": str(process.status()),
                "cpu_percent_over_interval": None,
            }
        checked_process(psutil_module, identity)
        if previous is not None:
            delta_wall = elapsed_seconds - previous["elapsed_seconds"]
            old = previous["processes"][name]
            delta_cpu = cpu.user + cpu.system - old["cpu_user_seconds"] - old["cpu_system_seconds"]
            if delta_wall <= 0 or delta_cpu < -1e-6:
                raise LeaseChanged("Bound process clock or cumulative CPU counters went backwards")
            rows[name]["cpu_percent_over_interval"] = 100 * max(0, delta_cpu) / delta_wall
    memory = psutil_module.virtual_memory()
    return {"schema": "native-resource-sample-v1", "recorded_utc": utc(),
            "elapsed_seconds": elapsed_seconds,
            "system_ram": {"total_bytes": int(memory.total), "available_bytes": int(memory.available)},
            "processes": rows}


def verify_bound_inputs(binding):
    for item in binding["inputs"].values():
        if sha_file(item["path"]) != item["sha256"]:
            raise LeaseChanged("A bound launch or render input changed")
    if sha_file(binding["script"]["path"]) != binding["script"]["sha256"]:
        raise LeaseChanged("Observer source changed during observation")


def seal_output(directory):
    files = {path.relative_to(directory).as_posix(): sha_file(path)
             for path in sorted(directory.rglob("*")) if path.is_file()}
    write_new(directory / "manifest.json", {
        "schema": "native-resource-observer-manifest-v1", "complete": True, "files": files,
    })


def observe(binding, output, stop_file, interval_seconds, psutil_module, *,
            monotonic=time.monotonic, sleep=time.sleep, stop_requested=lambda: None):
    """Observe until an explicit stop or lease failure; never control either process."""
    if not math.isfinite(interval_seconds) or interval_seconds <= 0:
        raise ValueError("Sampling interval must be positive and finite")
    output, stop_file = Path(output).resolve(), Path(stop_file).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "observer-binding.json", {**binding,
              "interval_seconds": interval_seconds, "stop_file": str(stop_file)})
    with (output / "observer.source.py").open("xb") as stream:
        stream.write(Path(binding["script"]["path"]).read_bytes())
    for name, item in binding["inputs"].items():
        with (output / f"{name}.source.json").open("xb") as stream:
            stream.write(Path(item["path"]).read_bytes())
    started = monotonic()
    summary = {"schema": "native-resource-observer-summary-v1", "started_utc": utc(),
               "samples": 0, "minimum_sampled_available_ram_bytes": None,
               "maximum_sampled_rss_bytes": {name: None for name in binding["processes"]},
               "terminal_reason": None, "actual_generation_requests": 0, "network_requests": 0}
    previous = None
    exit_code = 0
    try:
        with (output / "resources.jsonl").open("x", encoding="utf-8", newline="\n") as journal:
            while True:
                requested = stop_requested()
                if requested:
                    summary["terminal_reason"] = requested
                    exit_code = 130
                    break
                if stop_file.exists():
                    summary["terminal_reason"] = "explicit_stop_file"
                    break
                verify_bound_inputs(binding)
                row = sample_resources(binding, psutil_module, monotonic() - started, previous)
                row["sample_index"] = summary["samples"]
                journal.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                journal.flush()
                os.fsync(journal.fileno())
                summary["samples"] += 1
                available = row["system_ram"]["available_bytes"]
                old_available = summary["minimum_sampled_available_ram_bytes"]
                summary["minimum_sampled_available_ram_bytes"] = (
                    available if old_available is None else min(available, old_available))
                for name, process_row in row["processes"].items():
                    old_peak = summary["maximum_sampled_rss_bytes"][name]
                    summary["maximum_sampled_rss_bytes"][name] = (
                        process_row["rss_bytes"] if old_peak is None
                        else max(old_peak, process_row["rss_bytes"]))
                previous = row
                due = monotonic() + interval_seconds
                while monotonic() < due and not stop_file.exists() and not stop_requested():
                    sleep(min(1, max(0, due - monotonic())))
    except (LeaseChanged, psutil_module.NoSuchProcess, psutil_module.ZombieProcess) as error:
        summary["terminal_reason"] = "bound_lease_changed"
        summary["error"] = {"type": type(error).__name__, "message": str(error)}
        exit_code = 2
    except KeyboardInterrupt:
        summary["terminal_reason"] = "keyboard_interrupt"
        exit_code = 130
    except Exception as error:
        summary["terminal_reason"] = "observation_error"
        summary["error"] = {"type": type(error).__name__, "message": str(error)}
        exit_code = 1
    finally:
        summary["finished_utc"] = utc()
        summary["elapsed_seconds"] = monotonic() - started
        summary["stream_closed"] = True
        summary["pilot_completion_not_assessed"] = True
        write_new(output / "terminal-summary.json", summary)
        seal_output(output)
    return exit_code, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", type=Path, required=True)
    parser.add_argument("--render-binding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New exclusive output directory")
    parser.add_argument("--stop-file", type=Path, required=True, help="Explicit path to touch to stop")
    parser.add_argument("--interval-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    import psutil
    binding = prepare_binding(args.launch, args.render_binding, psutil)
    received = []

    def request_stop(signum, frame):
        received.append(f"signal_{signum}")

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, request_stop)
    code, summary = observe(binding, args.output, args.stop_file, args.interval_seconds, psutil,
                            stop_requested=lambda: received[0] if received else None)
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
