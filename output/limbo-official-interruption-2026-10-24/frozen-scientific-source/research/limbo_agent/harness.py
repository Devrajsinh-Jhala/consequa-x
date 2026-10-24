"""One-shot, serial, subprocess-isolated LIMBO collection.

No native task, environment, fault or grader implementation is changed. Scoped
API instrumentation records actual work including verification and late flush.
The trusted evaluator retains gold; model and policy receive native public data.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from .protocol import (canonical, environment_binding, file_binding, source_binding, utc, verify_files,
                       verify_protocol, write_new)


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, set):
        return sorted(plain(v) for v in value)
    if isinstance(value, dict):
        if all(type(k) is str for k in value):
            return {k: plain(v) for k, v in value.items()}
        return {"__mapping_pairs__": sorted([[plain(k), plain(v)] for k, v in value.items()],
                                           key=lambda pair: canonical(pair[0]))}
    raise TypeError("Non-serializable trusted state: " + type(value).__name__)


def world_state(world):
    values = {key: value for key, value in vars(world).items() if key not in ("rng", "deferred")}
    values["rng_state"] = world.rng.getstate()
    values["deferred"] = [[due, seq, meta] for due, seq, _callback, meta in world.deferred]
    return plain(values)


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = self.path.open("x", encoding="utf-8", newline="\n")

    def __call__(self, value):
        self.stream.write(json.dumps(plain(value), sort_keys=True, allow_nan=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


@contextmanager
def record_runtime(journal, work_limits=None):
    """Record enter/return nesting; shadow/dry-run worlds are excluded."""
    from limbo.runtime import ToolRuntime
    from limbo.world import World
    original_init = ToolRuntime.__init__
    originals = {name: getattr(ToolRuntime, name) for name in ("execute", "verify", "flush")}
    original_advance = World.advance
    work_limits = work_limits or {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800}
    state = {"runtime": None, "initial_world": None, "stack": [], "next_id": 0,
             "counts": {"execute": 0, "verify": 0, "advance": 0}, "wait_seconds": 0.0}

    def initialize(rt, *args, **kwargs):
        original_init(rt, *args, **kwargs)
        if state["runtime"] is not None:
            raise RuntimeError("More than one native world in an episode subprocess")
        state["runtime"] = rt
        state["initial_world"] = world_state(rt.world)

    def wrapped(op, method):
        def call(obj, *args, **kwargs):
            rt = state["runtime"]
            if rt is None or (op == "advance" and obj is not rt.world):
                return method(obj, *args, **kwargs)
            if op == "verify" and kwargs.get("truth", False) is not False:
                raise ValueError("Privileged verification is prohibited")
            ident = state["next_id"]
            state["next_id"] += 1
            bound = inspect.signature(method).bind(obj, *args, **kwargs)
            bound.apply_defaults()
            values = bound.arguments
            normalized_args = ([values["name"], values["args"]] if op == "execute" else
                               [values["name"], values["args"], values["t_call"]] if op == "verify" else
                               [values["seconds"]] if op == "advance" else [])
            normalized_kwargs = ({"source": values["source"], "note": values["note"]} if op == "execute" else
                                 {"truth": values["truth"]} if op == "verify" else {})
            entry = {"event": "enter", "id": ident,
                     "parent": state["stack"][-1] if state["stack"] else None,
                     "op": op, "args": plain(normalized_args), "kwargs": plain(normalized_kwargs),
                     "clock": rt.world.clock}
            journal(entry)
            state["stack"].append(ident)
            try:
                if op in ("execute", "verify"):
                    state["counts"][op] += 1
                    if state["counts"][op] > work_limits[op]:
                        raise RuntimeError("Uniform native " + op + " budget exhausted")
                if op == "advance" and entry["parent"] is None:
                    state["counts"]["advance"] += 1
                    state["wait_seconds"] += float(args[0] if args else kwargs["seconds"])
                    if state["counts"]["advance"] > work_limits["wait"] or state["wait_seconds"] > work_limits["total_wait_seconds"]:
                        raise RuntimeError("Uniform native wait budget exhausted")
                value = method(obj, *args, **kwargs)
            except BaseException as exc:
                journal({"event": "raise", "id": ident, "type": type(exc).__name__,
                         "message": str(exc), "clock": rt.world.clock})
                raise
            else:
                journal({"event": "return", "id": ident, "result": plain(value),
                         "clock": rt.world.clock})
                return value
            finally:
                state["stack"].pop()
        return call

    ToolRuntime.__init__ = initialize
    for name, original in originals.items():
        setattr(ToolRuntime, name, wrapped(name, original))
    World.advance = wrapped("advance", original_advance)
    try:
        yield state
    finally:
        ToolRuntime.__init__ = original_init
        for name, original in originals.items():
            setattr(ToolRuntime, name, original)
        World.advance = original_advance


def installed_wheel_binding(wheel):
    """Check every actual package payload byte, excluding installer-generated metadata."""
    from .policy import audit_framework_wheel
    return audit_framework_wheel(wheel)


def run_episode_worker(root, native_root, config_path, output):
    """Only child entry point; no stock runner retries or parallelism."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    protocol, slot = config["protocol"], config["slot"]
    verify_files(root, protocol["sources"])
    if canonical(protocol["sources"]) != canonical(source_binding(root)):
        raise ValueError("Scientific source inventory changed")
    verify_files(native_root, protocol["native"]["files"])
    if canonical(protocol["environment"]) != canonical(environment_binding()):
        raise ValueError("Interpreter/dependency environment changed")
    output = Path(output)
    sys.path.insert(0, str(Path(native_root).resolve()))
    from limbo import agent
    from .boundary import BoundaryLimits
    from .policy import make_policy
    from .transport import AuditedLIMBOClient, RuntimeBinding
    wheel = installed_wheel_binding(protocol["wheel"]["path"])
    write_new(output / "installed-wheel.json", wheel)
    runtime_journal, framework_journal = Journal(output / "runtime.jsonl"), Journal(output / "framework.jsonl")
    original_factory = agent.make_policy
    limits = BoundaryLimits(**protocol["limits"]["work"])
    agent.make_policy = lambda name, episode_id: make_policy(name, episode_id,
                                                            journal=framework_journal, limits=limits)
    budget = protocol["limits"]
    deadline = time.monotonic() + budget["episode_timeout_s"]
    try:
        with record_runtime(runtime_journal, budget["work"]) as state:
            with AuditedLIMBOClient(RuntimeBinding.from_dict(protocol["runtime_binding"]),
                                   output / "model", max_requests=budget["max_requests"],
                                   max_output_tokens=budget["max_output_tokens"],
                                   request_timeout_s=budget["request_timeout_s"],
                                   seed=protocol["seed"], absolute_deadline_monotonic=deadline,
                                   protected_roots=(str(Path(native_root).resolve()),
                                                    str(Path(protocol["runtime_binding"]["model_blob"]).parent))) as client:
                result = agent.run_episode(agent.EpisodeSpec(**slot["spec"]), client=client)
            rt = state["runtime"]
            if rt is None:
                raise RuntimeError("Native environment was not constructed")
            write_new(output / "world.json", {"initial": state["initial_world"],
                                              "final": world_state(rt.world)})
            write_new(output / "native-result.json", result)
            write_new(output / "worker-terminal.json", {"status": "native_returned", "utc": utc(),
                       "native_error": result["error"], "stop_reason": result["stop_reason"],
                       "runtime_events": state["next_id"]})
    except BaseException as exc:
        write_new(output / "worker-terminal.json", {"status": "worker_failed", "utc": utc(),
                  "error": type(exc).__name__ + ": " + str(exc),
                  "traceback": traceback.format_exc(limit=8)})
        raise
    finally:
        agent.make_policy = original_factory
        runtime_journal.close()
        framework_journal.close()


def manifest(directory):
    directory = Path(directory)
    return {str(p.relative_to(directory)).replace("\\", "/"): file_binding(p)
            for p in sorted(directory.rglob("*")) if p.is_file() and p != directory / "manifest.json"}


def clean_environment(root, native_root):
    allow = ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT",
             "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
    result = {k: v for k, v in os.environ.items() if k.upper() in allow}
    result.update(PYTHONPATH=os.pathsep.join((str(root), str(native_root))),
                  PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", NO_PROXY="127.0.0.1,localhost",
                  no_proxy="127.0.0.1,localhost", LIMBO_API_KEY="local-no-secret")
    return result


def execute_slot(root, native_root, protocol, slot, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    config_path = output / "worker-config.json"
    write_new(config_path, {"protocol": protocol, "slot": slot})
    args = [sys.executable, "-B", str(Path(root) / "scripts/run_limbo_external_benchmark.py"),
            "_episode", "--native-root", str(native_root), "--config", str(config_path),
            "--output", str(output)]
    started = utc()
    disposition, exit_code = "started_unknown", None
    with (output / "stdout.log").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
        process = subprocess.Popen(args, cwd=root, env=clean_environment(root, native_root),
                                   stdout=stdout, stderr=stderr)
        try:
            exit_code = process.wait(timeout=protocol["limits"]["episode_timeout_s"])
            disposition = "child_returned" if exit_code == 0 else "child_failed"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            exit_code, disposition = process.returncode, "parent_deadline"
    record = {"slot": slot["slot"], "world_rank": slot["world_rank"], "arm": slot["arm"],
              "status": disposition, "started_utc": started, "ended_utc": utc(),
              "exit_code": exit_code, "directory": output.name}
    write_new(output / "parent-terminal.json", record)
    write_new(output / "manifest.json", manifest(output))
    return record


def collect(root, native_root, protocol_path, protocol_commit, output):
    protocol = verify_protocol(root, native_root, protocol_path, protocol_commit)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "claim.json", {"utc": utc(), "protocol_commit": protocol_commit,
                                      "protocol_sha256": file_binding(protocol_path)["sha256"],
                                      "retry_resume_replacement": False})
    write_new(output / "protocol.json", protocol)
    rows = []
    stopped = None
    for slot in protocol["schedule"]:
        try:
            verify_files(root, protocol["sources"])
            if canonical(protocol["sources"]) != canonical(source_binding(root)):
                raise ValueError("Scientific source inventory changed")
            verify_files(native_root, protocol["native"]["files"])
        except Exception as exc:
            stopped = type(exc).__name__ + ": " + str(exc)
        if stopped is not None:
            rows.append({"slot": slot["slot"], "world_rank": slot["world_rank"],
                         "arm": slot["arm"], "status": "unstarted_integrity_stop", "reason": stopped})
            continue
        rows.append(execute_slot(root, native_root, protocol, slot,
                                 output / f"slot-{slot['slot']:03d}"))
        write_new(output / f"disposition-{slot['slot']:03d}.json", rows[-1])
        print(json.dumps({"slot_completed": slot["slot"], "planned": len(protocol["schedule"]),
                          "disposition": rows[-1]["status"]}), flush=True)
    write_new(output / "collection.json", {"schema": "conseqax-limbo-collection-v1", "utc": utc(),
               "protocol_commit": protocol_commit, "rows": rows, "integrity_stop": stopped})
    write_new(output / "manifest.json", manifest(output))
    return rows
