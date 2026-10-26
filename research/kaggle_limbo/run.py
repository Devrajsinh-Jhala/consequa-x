"""Serial GPU collection with immutable per-slot checkpoints and offline audits."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback
import uuid

from .bundle import binding, verify
from .checkpoint import CheckpointStore, SessionBudget, atomic_bytes, canonical, load


def require(condition, message):
    if not condition:
        raise ValueError(message)


def protocol_from(study):
    record = verify(study)
    protocol = load(Path(study) / "study-design.json")
    from research.expanded_limbo.protocol import verify_protocol_structure
    verify_protocol_structure(protocol)
    require(protocol["counts"]["planned_slots"] == 3456, "The full matrix must retain all 3,456 slots")
    require(protocol["limits"]["episode_timeout_s"] == 1800
            and protocol["limits"]["request_timeout_s"] == 300,
            "Kaggle GPU trajectory/request deadlines differ from the frozen design")
    return record, protocol


def make_lineage(study, condition):
    record, protocol = protocol_from(study)
    return {"schema": "conseqax-kaggle-lineage-v1", "source_commit": record["source_commit"],
            "bundle_manifest": binding(Path(study) / "bundle-manifest.json"),
            "protocol": binding(Path(study) / "study-design.json"),
            "condition": condition, "cohort": "expanded-kaggle-gpu-v1",
            "cpu_cohorts_pooled": False}, protocol


def export_checkpoint(store):
    """Latest portable ZIP lives outside the evidence tree; old exports are retained."""
    state = store.snapshot()
    parent = store.root.parent
    destination = parent / "checkpoint.zip"
    tip = state["last_event_sha256"] or "empty"
    receipt = parent / "checkpoint-export.json"
    if destination.exists() and receipt.exists():
        prior = load(receipt)
        if prior.get("state") == state and binding(destination) == prior.get("archive"):
            return destination
        archive_dir = parent / "checkpoint-history"
        archive_dir.mkdir(exist_ok=True)
        archived = archive_dir / ("checkpoint-" + prior["archive"]["sha256"] + ".zip")
        if not archived.exists():
            destination.rename(archived)
        else:
            require(binding(destination) == binding(archived), "Existing export archive conflicts")
            destination.unlink()
    elif destination.exists():
        raise ValueError("Existing checkpoint ZIP has no bound export receipt")
    store.export(destination)
    atomic_bytes(receipt, canonical({"state": state, "archive": binding(destination),
                                    "tip": tip}), replace=receipt.exists())
    return destination


def summary(store):
    groups = defaultdict(lambda: {"planned": 0, "started": 0, "graded": 0, "TS": 0, "EOS": 0,
                                  "unavailable": 0, "normal_returns": 0})
    for slot in store.schedule:
        key = slot["model_id"] + " / " + slot["arm"]
        group = groups[key]
        group["planned"] += 1
        group["started"] += slot["slot"] in store.reservations
        terminal = store.terminals.get(slot["slot"])
        details = terminal.get("details", {}) if terminal else {}
        audit = details.get("audit", {})
        if audit.get("passed") and audit.get("grade_available"):
            group["graded"] += 1
            group["TS"] += audit["native_grade"]["TS"] is True
            group["EOS"] += audit["native_grade"]["EOS"] is True
            group["normal_returns"] += audit["normal_execution_return"] is True
        else:
            group["unavailable"] += 1
    return {"schema": "conseqax-kaggle-progress-v1", "state": store.snapshot(), "groups": dict(groups),
            "interpretation": "Finite all-planned counts; unavailable is not a fabricated semantic failure; no population significance or superiority inferred"}


def run_worker(config_path):
    config = load(config_path)
    study, output = Path(config["study_dir"]), Path(config["output"])
    lineage, protocol = make_lineage(study, config["condition"])
    require(lineage == config["lineage"], "Worker lineage changed")
    slot = protocol["schedule"][config["slot"]]
    native = study / "native"
    sys.path.insert(0, str(native))
    from limbo import agent
    from research.expanded_limbo.harness import PolicyOperationJournal, RecordedPolicy
    from research.limbo_agent.boundary import BoundaryLimits
    from research.limbo_agent.harness import Journal, record_runtime, world_state
    from research.limbo_agent.policy import audit_framework_wheel
    from research.limbo_agent.transport import RuntimeBinding
    from research.obligation_shield.policy import make_policy
    from .transport import KaggleGPUClient
    from .runtime import save
    lease = RuntimeBinding.from_dict(config["runtime"])
    require(lease.model == slot["model_id"], "Worker loaded another model")
    model = next(m for m in protocol["models"] if m["id"] == slot["model_id"])
    require(lease.model_blob_sha256 == model["weights"]["sha256"], "Worker model weights differ")
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("planned-slot.json", slot), ("specification.json", slot["spec"]),
                        ("worker-config.json", config)):
        save(output / name, value)
    wheel = next((study / "assets").glob("consequa_x-2.1.1-*.whl"))
    save(output / "installed-wheel.json", audit_framework_wheel(wheel))
    journals = {key: Journal(output / filename) for key, filename in {
        "runtime": "runtime.jsonl", "starts": "policy-starts.jsonl", "policy": "policy.jsonl",
        "evidence": "policy-evidence.jsonl"}.items()}
    recorder, original = PolicyOperationJournal(journals["runtime"]), agent.make_policy
    limits = protocol["limits"]

    def factory(name, identity):
        policy = make_policy(name, identity, journal=journals["evidence"],
                             limits=BoundaryLimits(**limits["work"]))
        return RecordedPolicy(policy, recorder, journals["starts"], journals["policy"])

    agent.make_policy = factory
    try:
        with record_runtime(recorder, limits["work"]) as state:
            with KaggleGPUClient(lease, output / "model", condition=config["condition"],
                    gpu_devices=config["gpu_devices"], gpu_load_proof=config["gpu_load_proof"],
                    max_requests=limits["max_requests"],
                    max_output_tokens=limits["max_output_tokens"], request_timeout_s=limits["request_timeout_s"],
                    seed=slot["generation_seed"], temperature=slot["temperature"],
                    absolute_deadline_monotonic=time.monotonic() + limits["episode_timeout_s"],
                    protected_roots=(str(native), str(Path(lease.model_blob).parent))) as client:
                result = agent.run_episode(agent.EpisodeSpec(**slot["spec"]), client=client)
            require(state["runtime"] is not None, "Native world was not constructed")
            save(output / "world.json", {"initial": state["initial_world"],
                                       "final": world_state(state["runtime"].world)})
            save(output / "native-result.json", result)
            save(output / "worker-terminal.json", {"status": "native_returned",
                "native_error": result["error"], "stop_reason": result["stop_reason"]})
    except BaseException as exc:
        if not (output / "worker-terminal.json").exists():
            save(output / "worker-terminal.json", {"status": "worker_failed",
                "error": type(exc).__name__ + ": " + str(exc), "traceback": traceback.format_exc(limit=10)})
        raise
    finally:
        agent.make_policy = original
        for journal in journals.values():
            journal.close()


def execute_episode(study, output, slot, lineage, runtime, devices, timeout, gpu_load_proof=None):
    """The reservation exists before this child can issue any model/tool request."""
    from research.limbo_agent.harness import manifest
    from .runtime import save
    config = {"study_dir": str(study), "output": str(output), "slot": slot["slot"],
              "lineage": lineage, "condition": lineage["condition"],
              "runtime": asdict(runtime), "gpu_devices": devices, "gpu_load_proof": gpu_load_proof}
    config_path = output.parent / "execution-config.json"
    save(config_path, config)
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN"))
                   and key.upper() not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}}
    environment.update(PYTHONPATH=os.pathsep.join((str(study), str(study / "native"))),
        PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", NO_PROXY="127.0.0.1,localhost")
    child = None
    status, code = "failed", None
    try:
        with (output / "stdout.log").open("xb") as out, (output / "stderr.log").open("xb") as err:
            child = subprocess.Popen([sys.executable, "-B", "-m", "research.kaggle_limbo.run",
                "--worker-config", str(config_path)], cwd=study, env=environment,
                stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            try:
                code = child.wait(timeout=timeout)
                status = "returned" if code == 0 else "failed"
            except subprocess.TimeoutExpired:
                status = "interrupted"
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=30)
        save(output / "parent-terminal.json", {"status": status, "exit_code": code,
             "slot": slot["slot"], "no_automatic_retry": True})
        save(output / "manifest.json", manifest(output))
    return status


def preflight(study, root, protocol, setup):
    """Task-independent GPU render and tiny live tool-call tests, excluded from outcomes."""
    from .runtime import load_model, save
    from .transport import KaggleGPUClient
    from research.limbo_agent.harness import plain
    records = {}
    tool = {"name": "lookup_echo", "description": "An invented read-only transport check.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}},
                           "required": ["name"]}}
    session_root = root / "sessions" / uuid.uuid4().hex
    session_root.mkdir(parents=True, exist_ok=False)
    for model in protocol["models"]:
        current = session_root / model["family"]
        lease = load_model(setup["server"], model, current / "lease")
        with KaggleGPUClient(lease, current / "client", condition=setup["condition"],
                gpu_devices=setup["gpu_devices"], gpu_load_proof=load(current / "lease/gpu-load-proof.json"),
                max_requests=1, max_output_tokens=128,
                request_timeout_s=300, temperature=.2, seed=2501) as client:
            turn = client.complete("Call lookup_echo exactly once with the requested name. Do not answer in prose.",
                [{"role": "user", "content": "Call lookup_echo with name test-item"}], [tool])
            save(current / "parsed-turn.json", plain(turn))
            require(len(turn.tool_calls) == 1 and turn.tool_calls[0].name == "lookup_echo"
                    and turn.tool_calls[0].parsed_arguments() == ({"name": "test-item"}, None),
                    "Model/tool transport preflight failed; no measured episodes were started")
        save(current / "preflight.json", {"passed": True, "native_tasks": 0,
            "actual_model_dispatches": 1, "condition": setup["condition"], "model_id": model["id"]})
        records[model["id"]] = binding(current / "preflight.json")
    return records


def collect(study, output, *, session_hours=7, resume_from=None):
    from . import runtime as gpu
    from .audit import audit_kaggle_episode
    from research.limbo_agent.harness import manifest
    study, output = Path(study).resolve(), Path(output).resolve()
    setup_path = Path(os.environ.get("CONSEQAX_RUNTIME_DIR", "/kaggle/temp/conseqax-runtime")) / "setup.json"
    setup = load(setup_path)
    require(gpu.condition(gpu.gpu_inventory()) == setup["condition"], "GPU/setup condition changed")
    lineage, protocol = make_lineage(study, setup["condition"])
    started = float(os.environ.get("CONSEQAX_SESSION_START_MONOTONIC", time.monotonic()))
    require(math.isfinite(started) and 0 <= started <= time.monotonic(),
            "The first-cell session timestamp is invalid or in the future")
    require(0 < session_hours <= 7, "Use at most seven hours inside the eight-hour session")
    budget = SessionBudget(seconds=session_hours * 3600, flush_margin=1800,
                           episode_allowance=protocol["limits"]["episode_timeout_s"], started_at=started)
    current_lease, current_model, current_gpu_proof = None, None, None
    session_id = uuid.uuid4().hex
    with CheckpointStore(output, lineage, protocol["schedule"]) as store:
        if resume_from:
            store.import_snapshot(resume_from, allow_live_tree=Path(resume_from).is_dir())
        store.reconcile_orphans(resuming_session_id=session_id)
        try:
            if not budget.can_start_next():
                print("Session budget exhausted during setup; exporting without starting an episode.", flush=True)
                return
            store.begin_session(session_id, {"condition": setup["condition"], "gpu_devices": setup["gpu_devices"]})
            if not (output / "frozen-study.json").exists():
                gpu.save(output / "frozen-study.json", {"protocol": protocol, "lineage": lineage,
                    "frozen_before_measured_generation": True,
                    "public_preregistration_claim": False})
            proofs = preflight(study, output, protocol, setup)
            gpu.save(output / "sessions" / (session_id + "-readiness.json"), {
                "passed": True, "model_preflights": proofs, "native_tasks": 0,
                "condition": setup["condition"], "before_any_new_measured_slot": True})
            declaration = output / "execution-declaration.json"
            if not declaration.exists():
                gpu.save(declaration, {"schema": "conseqax-kaggle-execution-declaration-v1",
                    "lineage": lineage, "planned_slots": len(protocol["schedule"]),
                    "readiness": binding(output / "sessions" / (session_id + "-readiness.json")),
                    "source_model_and_schedule_manifest": binding(study / "bundle-manifest.json"),
                    "before_first_measured_generation": True, "public_preregistration_claim": False})
            while budget.can_start_next():
                if shutil.disk_usage(output).free < 2 * 1024**3:
                    print("Stopping before storage is exhausted; exporting the complete checkpoint.", flush=True)
                    break
                slot = store.next_unstarted()
                if slot is None:
                    break
                if current_model != slot["model_id"]:
                    model = next(m for m in protocol["models"] if m["id"] == slot["model_id"])
                    lease_path = output / "sessions" / session_id / ("lease-" + str(slot["slot"]))
                    current_lease = gpu.load_model(setup["server"], model, lease_path)
                    current_gpu_proof = load(lease_path / "gpu-load-proof.json")
                    current_model = slot["model_id"]
                budget.require_start()
                store.reserve(slot["slot"], session_id, budget=budget)
                episode = store.slot_directory(slot["slot"])
                details, status = {}, "failed"
                try:
                    returned = execute_episode(study, episode, slot, lineage, current_lease,
                        setup["gpu_devices"], protocol["limits"]["episode_timeout_s"],
                        gpu_load_proof=current_gpu_proof)
                    if returned == "returned" and (episode / "native-result.json").exists():
                        sys.path.insert(0, str(study / "native"))
                        audit = audit_kaggle_episode(episode, slot, lineage=lineage,
                            expected_limits=protocol["limits"], expected_model=model)
                        # Audit evidence is outside the already sealed episode.
                        gpu.save(episode.parent / "audit.json", audit)
                        details["audit"] = audit
                        status = "completed" if audit["normal_execution_return"] else "native_error_return"
                    else:
                        status = "interrupted" if returned == "interrupted" else "failed"
                except KeyboardInterrupt:
                    status = "interrupted"
                    raise
                except Exception as exc:
                    details["error"] = type(exc).__name__ + ": " + str(exc)
                    # Integrity errors do not authorize spending the remaining study.
                    status = "failed"
                    raise
                finally:
                    if not (episode / "manifest.json").exists():
                        gpu.save(episode / "manifest.json", manifest(episode))
                    store.finish(slot["slot"], status, details=details)
                progress = summary(store)
                atomic_bytes(output.parent / "progress.json", canonical(progress),
                             replace=(output.parent / "progress.json").exists())
                print(json.dumps({"slot": slot["slot"], "status": status,
                    "finished": len(store.terminals), "planned": len(store.schedule),
                    "remaining_session_minutes": round(budget.remaining / 60, 1)}), flush=True)
        finally:
            try:
                gpu.unload()
            except Exception as exc:
                print("Model unload failed; preserving the checkpoint:", type(exc).__name__, flush=True)
            archive = export_checkpoint(store)
            atomic_bytes(output.parent / "progress.json", canonical(summary(store)),
                         replace=(output.parent / "progress.json").exists())
            print("SAVE THIS NOTEBOOK VERSION WITH OUTPUTS. Checkpoint:", archive, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir")
    parser.add_argument("--output")
    parser.add_argument("--session-hours", type=float, default=7)
    parser.add_argument("--resume-from")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--worker-config")
    args = parser.parse_args()
    if args.worker_config:
        run_worker(args.worker_config)
    elif args.export_only:
        require(args.output and args.study_dir, "Study and output paths required")
        identity = load(Path(args.output) / "identity.json")
        protocol = protocol_from(args.study_dir)[1]
        with CheckpointStore(args.output, identity["lineage"], protocol["schedule"]) as store:
            print(export_checkpoint(store))
    else:
        require(args.output and args.study_dir, "Study and output paths required")
        collect(args.study_dir, args.output, session_hours=args.session_hours, resume_from=args.resume_from)


if __name__ == "__main__":
    main()
