"""Serial native external pilot, with exclusive prospective protocol and hard deadlines.

Run --help for phases. Development is confined to two excluded native tasks;
official collection requires an immutable committed source/protocol binding.
No GitHub workflow, hosted model, human participant or annotation is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.native_agent.protocol import (  # noqa: E402
    EXCLUDED, MODEL_DIGEST, RESEARCH_API_BASE, canonical_sha, load_json, make_schedule,
    runtime_binding, select_metadata, sha_file, source_binding, verify_files,
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def native_binding(native_root):
    from research.native_agent.audit import verify_native_source
    result = verify_native_source(native_root)
    for name in ("pyproject.toml", "uv.lock", "src/tau2/config.py"):
        path = Path(native_root) / name
        if path.is_file() and name not in result["files"]:
            expected = subprocess.check_output(["git", "-C", str(native_root), "show",
                                                result["commit"] + ":" + name])
            actual = path.read_bytes()
            if actual != expected and actual != expected.replace(b"\n", b"\r\n"):
                raise ValueError("Native project metadata differs from pin")
            result["files"][name] = {"runtime_sha256": sha_file(path),
                                     "git_sha256": __import__("hashlib").sha256(expected).hexdigest(),
                                     "runtime_bytes": len(actual), "git_bytes": len(expected)}
    return result


def verify_native_binding(native_root, binding):
    for name, record in binding["files"].items():
        path = (Path(native_root).resolve() / name).resolve()
        if not path.is_relative_to(Path(native_root).resolve()) or sha_file(path) != record["runtime_sha256"]:
            raise ValueError("Bound native runtime changed: " + name)


def runtime_gate(args, protocol=None):
    from research.native_agent.transport import (LocalOnlyGuard, ServerContextGate,
        configure_local_environment, read_gguf_metadata, tokenizer_from_gguf, MODEL_BLOB_SHA256)
    configure_local_environment(Path(args.native_root) / "data")
    if protocol:
        verify_files(ROOT, protocol["source"]["files"])
        verify_native_binding(args.native_root, protocol["native"])
        if runtime_binding(args.wheel) != protocol["runtime"]:
            raise ValueError("Native worker runtime differs from prospective freeze")
    guard = LocalOnlyGuard(protected_roots=(args.native_root, args.models), allow_generation=True,
                           allow_render_only=True, api_base=RESEARCH_API_BASE)
    guard.__enter__()
    try:
        httpx = guard.attach_httpx()
        import psutil
        from research.native_agent.transport import LOCAL_MODEL, CONTEXT_TOKENS
        launch = load_json(args.server_launch)
        server = psutil.Process(launch["server_pid"])
        if sha_file(server.exe()) != launch["server_executable_sha256"]:
            raise ValueError("Research server binary differs from launch receipt")
        blob = Path(args.models) / "blobs" / ("sha256-" + MODEL_BLOB_SHA256)
        runners = []
        for process in server.children():
            try:
                if Path(process.exe()).name == "llama-server.exe" and str(blob) in process.cmdline():
                    runners.append(process)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
        if len(runners) != 1:
            raise ValueError("Exactly one already loaded research model runner is required")
        runner = runners[0]
        cmd = runner.cmdline()
        guard.register_tokenizer_runner(port=int(cmd[cmd.index("--port") + 1]), pid=runner.pid,
            executable=runner.exe(), executable_sha256=sha_file(runner.exe()),
            model_blob=str(blob), model_blob_sha256=MODEL_BLOB_SHA256)
        with httpx.Client(trust_env=False, timeout=20) as client:
            version = client.get(guard.server_base + "/api/version").json()
            tags = client.get(guard.server_base + "/api/tags").json()
            resident = client.get(guard.server_base + "/api/ps").json()
        matching = [model for model in tags.get("models", []) if model.get("name") == LOCAL_MODEL]
        loaded = [model for model in resident.get("models", []) if model.get("name") == LOCAL_MODEL]
        if (version.get("version") != "0.40.6" or len(matching) != 1
                or matching[0].get("digest") != MODEL_DIGEST or len(loaded) != 1
                or loaded[0].get("context_length") != CONTEXT_TOKENS):
            raise ValueError("Model/tag/server/full-context identity changed or is not resident")
        metadata = read_gguf_metadata(blob)
        tokenizer = tokenizer_from_gguf(metadata)
        gate = ServerContextGate(guard, metadata, tokenizer)
        guard.before_generation = gate
        return guard, gate, {"version": version, "tag": matching[0], "resident": loaded[0],
                              "runner_binding": guard.tokenizer_runner,
                              "launch_receipt_sha256": sha_file(args.server_launch)}
    except BaseException:
        guard.__exit__(*sys.exc_info())
        raise


def worker(args):
    protocol = load_json(args.protocol) if args.protocol else None
    if protocol:
        row = protocol["schedule"][args.slot]
        if canonical_sha(protocol) != args.protocol_sha256:
            raise ValueError("Worker prospective protocol digest mismatch")
    else:
        if str(args.task_id) not in EXCLUDED or args.arm not in {"native", "G"}:
            raise ValueError("Development native tasks are restricted to excluded IDs 19/20")
        row = {"task_id": args.task_id, "arm": args.arm, "seed": 1701,
               "episode_id": "development-" + str(args.task_id) + "-" + args.arm}
    guard, gate, identity = runtime_gate(args, protocol)
    try:
        from research.native_agent.harness import run_episode
        status = run_episode(native_root=args.native_root, output=args.output,
            task_id=row["task_id"], arm=row["arm"], episode_id=row["episode_id"], seed=row["seed"],
            guard=guard, context_gate=gate, max_requests=args.max_requests,
            timeout_seconds=args.timeout)
        write_new(Path(args.output) / "worker-identity.json", identity)
        return 0 if status == "native_returned" else 1
    finally:
        guard.__exit__(None, None, None)


def transport_smoke(args):
    output = Path(args.output)
    output.mkdir(exist_ok=False, parents=True)
    guard = None
    result = {"started_utc": utc(), "official_tasks_read": 0, "generation_attempts": 0,
              "purpose": "task-independent structured-call and tool-result roundtrip", "passed": False}
    try:
        guard, gate, identity = runtime_gate(args)
        import httpx
        payload = load_json(args.wire)["observed"]["body"]
        payload.update(seed=1701, temperature=0, max_tokens=128, stream=False)
        payload["messages"][1]["content"] = (
            "Transport compatibility fixture: call get_reservation_details with reservation_id "
            "NATIVE_TRANSPORT_FIXTURE. This is a synthetic tool transport check.")
        payload["tool_choice"] = {"type": "function", "function": {"name": "get_reservation_details"}}
        responses = []
        with httpx.Client(trust_env=False, timeout=180) as client:
            for index in range(2):
                write_new(output / f"request-{index}.json", payload)
                result["generation_attempts"] += 1
                write_new(output / f"attempt-{index}.json", {"recorded_utc": utc(), "request": index})
                response = client.post(RESEARCH_API_BASE + "/chat/completions", json=payload)
                response.raise_for_status()
                body = response.json()
                write_new(output / f"response-{index}.json", body)
                responses.append(body)
                if index == 0:
                    message = body["choices"][0]["message"]
                    calls = message.get("tool_calls", [])
                    if (len(calls) != 1 or calls[0]["function"]["name"] != "get_reservation_details"
                            or json.loads(calls[0]["function"]["arguments"]) !=
                                {"reservation_id": "NATIVE_TRANSPORT_FIXTURE"}):
                        raise ValueError("Synthetic structured native-tool proposal did not match requested fixture")
                    payload["messages"].extend([message, {"role": "tool", "tool_call_id": calls[0]["id"],
                        "content": '{"reservation_id":"NATIVE_TRANSPORT_FIXTURE","status":"active","flights":[]}'},
                        {"role": "user", "content": "State the reservation ID and status returned by the tool."}])
                    payload["tool_choice"] = "none"
        result.update(passed=bool(responses[1]["choices"][0]["message"].get("content")), identity=identity,
                      context_checks=gate.receipts)
    except BaseException as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        if guard:
            result["network_events"] = guard.events
            guard.__exit__(None, None, None)
        result["finished_utc"] = utc()
        write_new(output / "transport-smoke-result.json", result)
    return 0 if result["passed"] else 1


def supervise(args, *, slot=None, protocol=None, maximum=None):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    episode = output / "episode"
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "worker",
        "--output", str(episode), "--native-root", args.native_root, "--models", args.models,
        "--wheel", args.wheel, "--server-launch", args.server_launch, "--timeout", str(args.timeout),
        "--max-requests", str(maximum or args.max_requests)]
    if protocol:
        command += ["--protocol", args.protocol, "--slot", str(slot),
                    "--protocol-sha256", canonical_sha(protocol)]
    else:
        command += ["--task-id", str(args.task_id), "--arm", args.arm]
    environment = dict(os.environ)
    environment.update(PYTHONPATH=str(ROOT) + os.pathsep + str(Path(args.native_root) / "src"),
                       PYTHONDONTWRITEBYTECODE="1", PYTHON_DOTENV_DISABLED="1")
    startup, flags = None, 0
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        flags = subprocess.CREATE_NO_WINDOW
    start = time.monotonic()
    with (output / "stdout.log").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
        process = subprocess.Popen(command, env=environment, cwd=ROOT, stdout=stdout, stderr=stderr,
                                   startupinfo=startup, creationflags=flags)
        write_new(output / "parent-start.json", {"started_utc": utc(), "pid": process.pid,
            "command": command, "hard_deadline_seconds": args.timeout, "corrective_reruns": 0})
        timed_out = False
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            code = process.wait(timeout=30)
    write_new(output / "parent-receipt.json", {"finished_utc": utc(), "exit_code": code,
        "hard_timeout": timed_out, "wall_seconds": time.monotonic() - start,
        "native_reward_available": (episode / "native-simulation.json").is_file(),
        "partial_artifacts_preserved": True})
    return code


def freeze(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    source = source_binding(ROOT)
    native = native_binding(args.native_root)
    metadata = select_metadata(load_json(Path(args.native_root) / "data/tau2/domains/airline/tasks.json"))
    readiness = load_json(args.readiness)
    if not readiness.get("passed"):
        raise ValueError("Explicit successful development readiness receipt required")
    protocol = {"schema": "conseqax-native-prospective-protocol-v1", "frozen_utc": utc(),
        "source": source, "native_root": str(Path(args.native_root).resolve()), "native": native,
        "runtime": runtime_binding(args.wheel), "selection": metadata, "schedule": make_schedule(metadata),
        "model": {"tag_digest": MODEL_DIGEST, "api_base": RESEARCH_API_BASE, "context_tokens": 16384,
            "kv_cache": "q8_0", "flash_attention": True, "temperature": 0, "seed": 1701,
            "max_output_tokens": 512, "render_tokenizer_gate": "every actual request, no truncation"},
        "ceilings": {"max_steps": 80, "max_consecutive_errors": 5, "max_requests": 48,
                     "request_timeout_seconds": 180, "hard_slot_timeout_seconds": 1200,
                     "provider_retries": 0, "runner_retries": 0},
        "readiness_receipt": {"path": str(Path(args.readiness).resolve()), "sha256": sha_file(args.readiness)},
        "server_launch": {"path": str(Path(args.server_launch).resolve()), "sha256": sha_file(args.server_launch)},
        "interpretation": {"B": "raw public readback controller with common instruction",
            "C": "classical current-field report plus conservative guard",
            "R": "ConseqaX2.1.1 current-field receipt without guard",
            "G": "ConseqaX2.1.1 current-field receipt plus same conservative guard",
            "distinct_task_ids": 12, "planned_slots": 48, "human_validation": False,
            "corpus_exposed_previously": True, "native_faults_injected": False,
            "claims_of_top_conference_readiness": False},
        "failure_law": "No replacement/retry/resume. Retain every planned slot; missing native reward unavailable and operational success0. Integrity mismatch stops collection with remaining slots unstarted. Ordinary model/context/time/resource failures remain slots; same frozen settings continue.",
        "analysis": "Native ALL DB+COMMUNICATE reward; every-call offline replay.12ID descriptive paired results only; no populationCI or free-form prose claim labels. Empty communication criteria separate. Field status and provenance distinct; provenance unknown."}
    write_new(out / "protocol.json", protocol)
    write_new(out / "protocol-receipt.json", {"protocol_sha256": canonical_sha(protocol),
              "protocol_file_sha256": sha_file(out / "protocol.json"), "frozen_utc": utc()})
    print(json.dumps({"protocol": str(out / "protocol.json"), "slots": 48, "source": source["commit"]}))
    return 0


def collect(args):
    protocol = load_json(args.protocol)
    if args.timeout != 1200 or args.max_requests != 48:
        raise ValueError("Official run must retain frozen ceilings")
    if source_binding(ROOT) != protocol["source"] or runtime_binding(args.wheel) != protocol["runtime"]:
        raise ValueError("Prospective source/runtime changed")
    verify_native_binding(args.native_root, protocol["native"])
    write_new(Path(args.protocol).parent / "exclusive-collection-claim.json",
              {"claimed_utc": utc(), "protocol_sha256": canonical_sha(protocol), "output": args.output})
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=False)
    dispositions, stopped = [], None
    original_output = args.output
    for row in protocol["schedule"]:
        if stopped:
            dispositions.append({**row, "status": "unstarted", "reason": stopped})
            continue
        try:
            verify_files(ROOT, protocol["source"]["files"])
            verify_native_binding(args.native_root, protocol["native"])
        except BaseException as exc:
            stopped = f"Integrity stop: {type(exc).__name__}: {exc}"
            dispositions.append({**row, "status": "unstarted", "reason": stopped})
            continue
        args.output = str(destination / f"slot-{row['slot']:03d}-{row['task_id']}-{row['arm']}")
        code = supervise(args, slot=row["slot"], protocol=protocol)
        dispositions.append({**row, "status": "worker_returned" if code == 0 else "execution_failed",
                             "exit_code": code})
        write_new(destination / f"disposition-{row['slot']:03d}.json", dispositions[-1])
        print(json.dumps(dispositions[-1]), flush=True)
    args.output = original_output
    write_new(destination / "collection-receipt.json", {"protocol_sha256": canonical_sha(protocol),
        "finished_utc": utc(), "all_planned_slots": dispositions, "integrity_stop": stopped,
        "corrective_reruns": 0, "complete_planned_matrix": len(dispositions) == 48})
    from research.native_agent.harness import seal_directory
    seal_directory(destination, "conseqax-native-collection-v1")
    return 0 if not stopped else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("transport-smoke", "development", "worker", "freeze", "collect"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--native-root", required=True)
    parser.add_argument("--models", default="C:/Users/DELL/.ollama/models")
    parser.add_argument("--wheel", required=True)
    parser.add_argument("--server-launch", required=True)
    parser.add_argument("--wire")
    parser.add_argument("--readiness")
    parser.add_argument("--protocol")
    parser.add_argument("--protocol-sha256")
    parser.add_argument("--task-id")
    parser.add_argument("--arm", default="native")
    parser.add_argument("--slot", type=int)
    parser.add_argument("--max-requests", type=int, default=48)
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    if args.phase == "worker":
        return worker(args)
    if args.phase == "transport-smoke":
        return transport_smoke(args)
    if args.phase == "development":
        if args.max_requests > 36:
            parser.error("Development allowance is at most36requests, tracked across retained attempts")
        return supervise(args)
    if args.phase == "freeze":
        return freeze(args)
    if args.phase == "collect":
        return collect(args)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
