"""New one-shot block collector, retaining all prefixes and planned dispositions.

Blocks are predeclared execution partitions. No measured slot is retried,
replaced or resumed. Only this trusted runner sees native worlds and task gold.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

from research.limbo_agent.boundary import BoundaryLimits
from research.limbo_agent.harness import (
    Journal, clean_environment, installed_wheel_binding, manifest, plain,
    record_runtime, world_state,
)
from research.limbo_agent.protocol import native_binding, utc, write_new
from research.limbo_agent.transport import RuntimeBinding

from .protocol import (
    NATIVE_PIN, canonical, file_binding, require, verify_protocol_structure,
)


POLICY_SCHEMA = "conseqax-expanded-limbo-policy-call-v1"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)))


def scientific_sources(root):
    """Complete current research source inventory, excluding unrelated product code."""
    root = Path(root).resolve()
    names = {p.relative_to(root).as_posix()
             for directory in ("research/expanded_limbo", "research/obligation_shield",
                               "research/limbo_agent")
             for p in (root / directory).glob("*.py")}
    names.update({"research/native_agent/transport.py", "research/native_agent/__init__.py",
                  "scripts/run_expanded_limbo.py"})
    if (root / "research/__init__.py").is_file():
        names.add("research/__init__.py")
    return {name: file_binding(root / name) for name in sorted(names)}


def verify_files(root, files):
    root = Path(root).resolve(strict=True)
    for name, expected in files.items():
        path = (root / name).resolve(strict=True)
        require(path.is_relative_to(root), "Bound file escapes its root")
        require(file_binding(path) == expected, "Bound file changed: " + name)


def committed_protocol(root, path, commit, *, reconstruct=True):
    root, path = Path(root).resolve(strict=True), Path(path).resolve(strict=True)
    require(path.is_relative_to(root), "Protocol must be inside research checkout")
    require(isinstance(commit, str) and len(commit) == 40
            and all(c in "0123456789abcdef" for c in commit), "Exact protocol commit required")
    relative = path.relative_to(root).as_posix()
    raw = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{relative}"],
                         check=True, capture_output=True).stdout
    require(raw == path.read_bytes(), "Protocol bytes differ from the committed artifact")
    protocol = load(path)
    if reconstruct:
        verify_protocol_structure(protocol)
    require(protocol["native_pin"] == NATIVE_PIN, "Pinned native source differs")
    require(scientific_sources(root) == protocol["sources"], "Research source inventory changed")
    verify_files(root, protocol["sources"])
    for name, expected in protocol["sources"].items():
        blob = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{name}"],
                              check=True, capture_output=True).stdout
        import hashlib
        require({"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)} == expected,
                "Scientific source is not in the protocol commit: " + name)
    return protocol


def verify_native(native_root, protocol):
    current = native_binding(native_root)
    require(current["commit"] == protocol["native_pin"]
            and current["files"] == protocol["native_sources"], "Native implementation changed")


def bound_runtime(protocol, model_id, runtime_file):
    binding = RuntimeBinding.from_dict(load(runtime_file))
    model = next((m for m in protocol["models"] if m["id"] == model_id), None)
    require(model is not None, "Unregistered model")
    require(binding.model == model_id and binding.context_tokens == model["context_tokens"],
            "Runtime alias/context differs from static model")
    require(binding.model_blob_sha256 == model["weights"]["sha256"], "Runtime weights differ")
    require(Path(binding.model_blob).stat().st_size == model["weights"]["bytes"],
            "Runtime weight bytes differ")
    require(binding.parallel_slots == 1, "Exactly one resident context slot required")
    return binding, model


def verify_readiness(protocol, path):
    """Bind the independent precollection receipt; null proposals cannot collect."""
    require(protocol.get("readiness") is not None, "An unfrozen readiness-free proposal cannot collect")
    require(file_binding(path) == protocol["readiness"], "Readiness receipt bytes changed")
    record = load(path)
    require(record.get("schema") == "conseqax-expanded-limbo-readiness-v1"
            and record.get("passed") is True, "Passed expanded readiness receipt required")
    for key in ("sources", "native_sources", "wheel", "models", "limits"):
        require(canonical(record.get(key)) == canonical(protocol[key]), "Readiness binding differs: " + key)
    return record


class PolicyOperationJournal:
    """Retain full native journal and each policy's top-level delegated operations."""

    def __init__(self, journal):
        self.journal = journal
        self.active = None
        self.pending = {}

    def __call__(self, record):
        self.journal(record)
        if self.active is None:
            return
        if record["event"] == "enter" and record["parent"] is None:
            if record["op"] in {"execute", "verify", "advance"}:
                self.pending[record["id"]] = {"op": record["op"],
                    "args": plain(record["args"]), "kwargs": plain(record["kwargs"])}
        elif record["event"] in {"return", "raise"} and record["id"] in self.pending:
            operation = self.pending.pop(record["id"])
            outcome = {"event": record["event"]}
            if record["event"] == "return":
                outcome["result"] = plain(record["result"])
            else:
                outcome.update(type=record["type"], message=record["message"])
            operation["outcome"] = outcome
            self.active.append(operation)


class RecordedPolicy:
    def __init__(self, policy, runtime_journal, starts, completed):
        self.policy = policy
        self.runtime_journal = runtime_journal
        self.starts, self.completed, self.sequence = starts, completed, 0
        self.name, self.prompt_variant, self.reflect = policy.name, policy.prompt_variant, policy.reflect

    @property
    def interventions(self):
        return self.policy.interventions

    def execute(self, runtime, name, args):
        require(self.runtime_journal.active is None, "Nested policy execution is refused")
        self.sequence += 1
        record = {"schema": POLICY_SCHEMA, "sequence": self.sequence,
                  "name": name, "args": plain(args), "clock_before": runtime.world.clock}
        self.starts({**record, "event": "policy_start"})
        operations = []
        self.runtime_journal.active = operations
        outcome = None
        try:
            result = self.policy.execute(runtime, name, args)
            outcome = {"event": "return", "result": plain(result)}
            return result
        except BaseException as error:
            outcome = {"event": "raise", "type": type(error).__name__, "message": str(error)}
            raise
        finally:
            self.runtime_journal.active = None
            record.update(clock_after=runtime.world.clock, operations=operations,
                outcome=outcome, interventions=plain(self.policy.interventions))
            self.completed(record)


def run_episode_worker(root, native_root, config_path, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    config = load(config_path)
    require(file_binding(config["protocol_path"]) == config["protocol_binding"], "Worker protocol changed")
    protocol = committed_protocol(root, config["protocol_path"], config["protocol_commit"], reconstruct=False)
    verify_readiness(protocol, Path(config["protocol_path"]).parent / "readiness.json")
    verify_native(native_root, protocol)
    require(file_binding(config["wheel_path"]) == protocol["wheel"], "Scientific wheel changed")
    require(file_binding(config["runtime_path"]) == config["runtime_binding_file"], "Runtime lease file changed")
    slot = protocol["schedule"][config["slot"]]
    require(slot["slot"] == config["slot"] and slot["block_id"] == config["block_id"], "Worker slot identity differs")
    binding, model = bound_runtime(protocol, slot["model_id"], config["runtime_path"])
    write_new(output / "specification.json", slot["spec"])
    write_new(output / "planned-slot.json", slot)
    write_new(output / "model-binding.json", {"model": model, "runtime": asdict(binding),
        "lease_file": {"path": config["runtime_path"], **config["runtime_binding_file"]}})
    write_new(output / "installed-wheel.json", installed_wheel_binding(config["wheel_path"]))
    sys.path.insert(0, str(Path(native_root).resolve()))
    from limbo import agent
    from research.obligation_shield.policy import make_policy
    from .transport import ExpandedLIMBOClient
    journals = {name: Journal(output / filename) for name, filename in {
        "runtime": "runtime.jsonl", "starts": "policy-starts.jsonl",
        "policy": "policy.jsonl", "evidence": "policy-evidence.jsonl"}.items()}
    recorder = PolicyOperationJournal(journals["runtime"])
    original_factory = agent.make_policy
    limits = protocol["limits"]

    def factory(name, episode_id):
        policy = make_policy(name, episode_id, journal=journals["evidence"],
                             limits=BoundaryLimits(**limits["work"]))
        return RecordedPolicy(policy, recorder, journals["starts"], journals["policy"])

    agent.make_policy = factory
    try:
        with record_runtime(recorder, limits["work"]) as state:
            with ExpandedLIMBOClient(binding, output / "model",
                    max_requests=limits["max_requests"], max_output_tokens=limits["max_output_tokens"],
                    request_timeout_s=limits["request_timeout_s"], seed=slot["generation_seed"],
                    temperature=slot["temperature"],
                    absolute_deadline_monotonic=time.monotonic() + limits["episode_timeout_s"],
                    protected_roots=(str(Path(native_root).resolve()), str(Path(binding.model_blob).parent))) as client:
                result = agent.run_episode(agent.EpisodeSpec(**slot["spec"]), client=client)
            runtime = state["runtime"]
            require(runtime is not None, "Native world was not constructed")
            write_new(output / "world.json", {"initial": state["initial_world"], "final": world_state(runtime.world)})
            write_new(output / "native-result.json", result)
            write_new(output / "worker-terminal.json", {"status": "native_returned", "utc": utc(),
                "native_error": result["error"], "stop_reason": result["stop_reason"],
                "runtime_events": state["next_id"]})
    except BaseException as error:
        if not (output / "worker-terminal.json").exists():
            write_new(output / "worker-terminal.json", {"status": "worker_failed", "utc": utc(),
                "error": type(error).__name__ + ": " + str(error), "traceback": traceback.format_exc(limit=8)})
        raise
    finally:
        agent.make_policy = original_factory
        for journal in journals.values():
            journal.close()


def execute_slot(root, native_root, config, output, limits):
    root, output = Path(root).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "worker-config.json", config)
    command = [sys.executable, "-B", str(root / "scripts/run_expanded_limbo.py"), "_episode",
        "--native-root", str(Path(native_root).resolve()), "--config", str(output / "worker-config.json"),
        "--output", str(output)]
    started, status, code = utc(), "started_unknown", None
    with (output / "stdout.log").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
        process = subprocess.Popen(command, cwd=root, env=clean_environment(root, native_root),
            stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        write_new(output / "child-process.json", {"pid": process.pid, "started_utc": started,
            "scope": "Fresh one-shot episode child; parent enforces the declared trajectory deadline"})
        try:
            code = process.wait(timeout=limits["episode_timeout_s"])
            status = "child_returned" if code == 0 else "child_failed"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            code, status = process.returncode, "parent_deadline"
    terminal = {"slot": config["slot"], "block_id": config["block_id"], "status": status,
        "started_utc": started, "ended_utc": utc(), "exit_code": code, "directory": output.name}
    write_new(output / "parent-terminal.json", terminal)
    write_new(output / "manifest.json", manifest(output))
    return terminal


def collect_block(root, native_root, protocol_path, protocol_commit, wheel_path,
                  runtime_path, block_id, output):
    """One exclusive reservation for one fixed block; started slots never repeat."""
    root, output = Path(root).resolve(), Path(output).resolve()
    protocol_path, wheel_path, runtime_path = [Path(p).resolve(strict=True)
                                             for p in (protocol_path, wheel_path, runtime_path)]
    require(not output.exists(), "Refuse an existing block output")
    protocol = committed_protocol(root, protocol_path, protocol_commit)
    verify_readiness(protocol, protocol_path.parent / "readiness.json")
    verify_native(native_root, protocol)
    require(file_binding(wheel_path) == protocol["wheel"], "Scientific wheel changed")
    installed_wheel_binding(wheel_path)
    block = next((b for b in protocol["blocks"] if b["block_id"] == block_id), None)
    require(block is not None, "Block is absent from the fixed plan")
    bound_runtime(protocol, block["model_id"], runtime_path)
    protocol_binding = file_binding(protocol_path)
    reservation_root = root / "output/expanded-limbo-reservations" / protocol_binding["sha256"]
    reservation_root.mkdir(parents=True, exist_ok=True)
    reservation_path = reservation_root / (block_id + ".json")
    claim = {"schema": "conseqax-expanded-limbo-block-claim-v1", "utc": utc(),
        "protocol": protocol_binding, "protocol_commit": protocol_commit,
        "block_id": block_id, "output": str(output), "replace_or_resume_started_slot": False}
    write_new(reservation_path, claim)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "claim.json", {**claim, "reservation_path": str(reservation_path),
                                      "reservation_binding": file_binding(reservation_path)})
    write_new(output / "block.json", block)
    write_new(output / "protocol-reference.json", {"path": str(protocol_path),
        **protocol_binding, "commit": protocol_commit})
    rows, stopped = [], None
    lease_file_binding = file_binding(runtime_path)
    slots = protocol["schedule"][block["first_slot"]:block["first_slot"] + block["slot_count"]]
    try:
        for slot in slots:
            if stopped is not None:
                rows.append({"slot": slot["slot"], "block_id": block_id,
                             "status": "unstarted_integrity_stop", "reason": stopped})
                continue
            config = {"protocol_path": str(protocol_path), "protocol_binding": protocol_binding,
                "protocol_commit": protocol_commit, "slot": slot["slot"], "block_id": block_id,
                "wheel_path": str(wheel_path), "runtime_path": str(runtime_path),
                "runtime_binding_file": lease_file_binding}
            try:
                # Never start a later slot after known source/native/lease changes.
                verify_files(root, protocol["sources"])
                require(file_binding(runtime_path) == config["runtime_binding_file"], "Lease changed")
                row = execute_slot(root, native_root, config, output / f"slot-{slot['slot']:05d}", protocol["limits"])
            except BaseException as error:
                stopped = type(error).__name__ + ": " + str(error)
                directory = output / f"slot-{slot['slot']:05d}"
                row = {"slot": slot["slot"], "block_id": block_id,
                    "status": "started_parent_error" if directory.exists() else "unstarted_integrity_stop",
                    "reason": stopped}
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    rows.append(row)
                    raise
            rows.append(row)
            write_new(output / f"disposition-{slot['slot']:05d}.json", row)
    finally:
        recorded = {row["slot"] for row in rows}
        for slot in slots:
            if slot["slot"] not in recorded:
                rows.append({"slot": slot["slot"], "block_id": block_id,
                    "status": "unstarted_after_collector_interruption"})
        rows.sort(key=lambda row: row["slot"])
        write_new(output / "collection.json", {"schema": "conseqax-expanded-limbo-block-collection-v1",
            "utc": utc(), "protocol": protocol_binding, "protocol_commit": protocol_commit,
            "block_id": block_id, "block_planned": len(slots),
            "entire_matrix_planned": protocol["counts"]["planned_slots"], "rows": rows,
            "stopped_reason": stopped, "no_retry_resume_replacement": True})
        write_new(output / "manifest.json", manifest(output))
    return {"block_id": block_id, "planned": len(slots), "rows": rows}
