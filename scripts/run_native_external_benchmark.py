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
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.native_agent.protocol import (  # noqa: E402
    EXCLUDED, MODEL_DIGEST, RESEARCH_API_BASE, SOURCE_PATHS, canonical_sha, load_json, make_schedule,
    runtime_binding, select_metadata, sha_file, source_binding, verify_files,
    verify_frozen_protocol,
)

INTEGRITY_EXIT = 78
DEVELOPMENT_CEILINGS = {"task_independent_transport": 12, "excluded_native": 36}


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def actual_source_files():
    return {name: {"sha256": sha_file(ROOT / name), "bytes": (ROOT / name).stat().st_size}
            for name in SOURCE_PATHS}


def reserve_development(args, category, maximum):
    """Exclusive persistent reservations precede every development child/request.

    An unfinished reservation consumes its full ceiling. The historical manual
    reservation is immutable and always consumes its full two requests.
    """
    if category not in DEVELOPMENT_CEILINGS or type(maximum) is not int or maximum < 1:
        raise ValueError("Invalid development category or reservation")
    directory = Path(args.development_ledger).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "exclusive-budget-lock"
    lock.mkdir(exist_ok=False)
    try:
        consumed = 0
        for path in directory.glob("*reservation-*.json"):
            record = load_json(path)
            if record.get("category") != category:
                continue
            amount = record["reserved_maximum_requests"]
            if type(amount) is not int or amount < 1:
                raise ValueError("Malformed retained development reservation")
            consumed += amount
            settlement_path = path.with_name(path.stem + ".settlement.json")
            if settlement_path.is_file():
                settlement = load_json(settlement_path)
                if settlement["reservation_sha256"] != sha_file(path):
                    raise ValueError("Development settlement no longer binds its reservation")
                for artifact in settlement["verified_artifacts"]:
                    if sha_file(artifact["path"]) != artifact["sha256"]:
                        raise ValueError("Development accounting artifact changed")
                released = settlement["released_unused_requests"]
                if type(released) is not int or not 0 <= released <= amount:
                    raise ValueError("Invalid development settlement release")
                consumed -= released
        ceiling = DEVELOPMENT_CEILINGS[category]
        if consumed + maximum > ceiling:
            raise ValueError(f"Shared {category} allowance exhausted: {consumed}+{maximum}>{ceiling}")
        path = directory / ("reservation-" + uuid.uuid4().hex + ".json")
        write_new(path, {"schema": "conseqax-native-development-reservation-v1", "recorded_utc": utc(),
            "category": category, "reserved_maximum_requests": maximum,
            "shared_category_ceiling": ceiling, "consumed_before": consumed,
            "output": str(Path(args.output).resolve()), "source_files": actual_source_files(),
            "task_id": getattr(args, "task_id", None), "arm": getattr(args, "arm", None),
            "unfinished_reservation_consumes_full_maximum": True})
        return path
    finally:
        lock.rmdir()


def settle_development(reservation_path, slot_output):
    """Release unused native allowance only from complete retained accounting."""
    reservation_path, output = Path(reservation_path), Path(slot_output)
    reservation = load_json(reservation_path)
    parent_path, execution_path = output / "parent-receipt.json", output / "episode/execution-receipt.json"
    calls_path = output / "episode/model-calls.jsonl"
    if not all(path.is_file() for path in (parent_path, execution_path, calls_path)):
        return False
    parent, execution = load_json(parent_path), load_json(execution_path)
    state = execution.get("model_requests")
    if (parent.get("exit_code") not in (0, 1) or parent.get("hard_timeout")
            or parent.get("supervisor_error") or execution.get("capture_errors")
            or execution.get("inflight_tool_dispatches") or not isinstance(state, dict)):
        return False
    rows = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
    starts = [row for row in rows if row.get("kind") == "request_start"]
    terminal = [row for row in rows if row.get("kind") in {"request_return", "request_error"}]
    attempted = state["attempted"]
    if (type(attempted) is not int or not 0 <= attempted <= reservation["reserved_maximum_requests"]
            or attempted != state["completed"] + state["failed"]
            or [row["call_index"] for row in starts] != list(range(attempted))
            or sorted(row["call_index"] for row in terminal) != list(range(attempted))):
        return False
    artifacts = (parent_path, execution_path, calls_path)
    write_new(reservation_path.with_name(reservation_path.stem + ".settlement.json"), {
        "schema": "conseqax-native-development-settlement-v1", "recorded_utc": utc(),
        "reservation_sha256": sha_file(reservation_path), "accounted_attempts": attempted,
        "released_unused_requests": reservation["reserved_maximum_requests"] - attempted,
        "verified_artifacts": [{"path": str(path.resolve()), "sha256": sha_file(path)} for path in artifacts]})
    return True


def verified_protocol(args):
    protocol, anchor = verify_frozen_protocol(args.protocol, args.protocol_commit)
    if getattr(args, "protocol_sha256", None) not in (None, anchor["protocol_sha256"]):
        raise ValueError("Worker prospective protocol digest mismatch")
    return protocol, anchor


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


def flag_value(command, *names):
    found = [command[index + 1] for index, item in enumerate(command[:-1]) if item in names]
    if len(found) != 1:
        raise ValueError("Missing or repeated required runtime flag " + "/".join(names))
    return found[0]


def verify_runner_configuration(command, blob, launch):
    environment = launch["process_only_environment"]
    parallel = int(environment["OLLAMA_NUM_PARALLEL"])
    if (parallel not in (1, 2) or environment.get("OLLAMA_HOST") != "127.0.0.1:11436"
            or environment.get("OLLAMA_KV_CACHE_TYPE") != "q8_0"
            or environment.get("OLLAMA_FLASH_ATTENTION") != "1"
            or environment.get("OLLAMA_CONTEXT_LENGTH") != "16384"
            or environment.get("OLLAMA_NO_CLOUD") != "1"
            or environment.get("OLLAMA_MAX_LOADED_MODELS") != "1"
            or Path(environment["OLLAMA_MODELS"]).resolve() != Path(blob).parents[1].resolve()):
        raise ValueError("Research launch does not declare the exact local q8 full-context condition")
    if (Path(flag_value(command, "--model")).resolve() != Path(blob).resolve()
            or flag_value(command, "--host") != "127.0.0.1"
            or flag_value(command, "--cache-type-k") != "q8_0"
            or flag_value(command, "--cache-type-v") != "q8_0"
            or flag_value(command, "--flash-attn") != "on"
            or int(flag_value(command, "-np", "--parallel")) != parallel
            or int(flag_value(command, "-c", "--ctx-size")) != 16384 * parallel
            or "--offline" not in command):
        raise ValueError("Actual model runner differs from declared cache/context configuration")
    return {"kv_cache_k": "q8_0", "kv_cache_v": "q8_0", "flash_attention": True,
            "context_tokens_per_slot": 16384, "cache_capacity_slots": parallel,
            "simultaneous_generation_clients": 1, "context_shift_runtime_capability": "--context-shift" in command}


def runtime_gate(args, protocol=None):
    from research.native_agent.transport import (LocalOnlyGuard, ServerContextGate,
        configure_local_environment, read_gguf_metadata, tokenizer_from_gguf, MODEL_BLOB_SHA256)
    configure_local_environment(Path(args.native_root) / "data")
    if protocol:
        if source_binding(ROOT) != protocol["source"]:
            raise ValueError("Execution source/root/commit differs from prospective freeze")
        verify_native_binding(args.native_root, protocol["native"])
        if runtime_binding(args.wheel) != protocol["runtime"]:
            raise ValueError("Native worker runtime differs from prospective freeze")
        for name in ("server_launch", "readiness_receipt"):
            record = protocol[name]
            if sha_file(record["path"]) != record["sha256"]:
                raise ValueError("Prospectively bound " + name + " changed")
        if Path(args.server_launch).resolve() != Path(protocol["server_launch"]["path"]).resolve():
            raise ValueError("Worker launch receipt differs from prospective freeze")
    guard = LocalOnlyGuard(protected_roots=(args.native_root, args.models), allow_generation=True,
                           allow_render_only=True, api_base=RESEARCH_API_BASE)
    guard.__enter__()
    try:
        httpx = guard.attach_httpx()
        import psutil
        from research.native_agent.transport import LOCAL_MODEL, CONTEXT_TOKENS
        launch = load_json(args.server_launch)
        server = psutil.Process(launch["server_pid"])
        if (Path(server.exe()).resolve() != Path(launch["server_executable"]).resolve()
                or sha_file(server.exe()) != launch["server_executable_sha256"]
                or server.cmdline()[1:] != launch["command"][1:]):
            raise ValueError("Research server binary differs from launch receipt")
        blob = Path(args.models) / "blobs" / ("sha256-" + MODEL_BLOB_SHA256)
        if sha_file(blob) != MODEL_BLOB_SHA256:
            raise ValueError("Actual GGUF model bytes differ from the declared digest")
        listeners = [connection for connection in server.net_connections(kind="tcp")
                     if connection.status == psutil.CONN_LISTEN
                     and connection.laddr.ip == "127.0.0.1" and connection.laddr.port == 11436]
        if len(listeners) != 1:
            raise ValueError("Recorded research server does not own the exact loopback listener")
        runners = []
        for process in server.children():
            try:
                command = process.cmdline()
                if (Path(process.exe()).name == "llama-server.exe"
                        and Path(flag_value(command, "--model")).resolve() == blob.resolve()):
                    runners.append(process)
            except (psutil.AccessDenied, psutil.NoSuchProcess, ValueError):
                pass
        if len(runners) != 1:
            raise ValueError("Exactly one already loaded research model runner is required")
        runner = runners[0]
        cmd = runner.cmdline()
        configuration = verify_runner_configuration(cmd, blob, launch)
        guard.register_tokenizer_runner(port=int(flag_value(cmd, "--port")), pid=runner.pid,
            executable=runner.exe(), executable_sha256=sha_file(runner.exe()),
            model_blob=str(blob), model_blob_sha256=MODEL_BLOB_SHA256)
        with httpx.Client(trust_env=False, timeout=20) as client:
            responses = [client.get(guard.server_base + path) for path in ("/api/version", "/api/tags", "/api/ps")]
            for response in responses:
                response.raise_for_status()
            version, tags, resident = [response.json() for response in responses]
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
        identity = {"version": version, "tag": matching[0], "resident": loaded[0],
                              "runner_binding": guard.tokenizer_runner,
                              "launch_receipt_sha256": sha_file(args.server_launch),
                              "server_executable": server.exe(), "server_executable_sha256": sha_file(server.exe()),
                              "server_create_time": server.create_time(), "runner_create_time": runner.create_time(),
                              "model_blob_sha256": MODEL_BLOB_SHA256,
                              "runner_configuration": configuration, "runner_command": cmd,
                              "source_files": actual_source_files()}
        if protocol:
            expected = protocol["runtime_identity"]
            for name in ("version", "tag", "launch_receipt_sha256", "server_executable_sha256",
                         "model_blob_sha256", "runner_configuration", "server_create_time", "runner_create_time"):
                if identity[name] != expected[name]:
                    raise ValueError("Actual runtime differs from frozen identity: " + name)
            if identity["runner_binding"] != expected["runner_binding"]:
                raise ValueError("Frozen private runner lease/identity changed")
        return guard, gate, identity
    except BaseException:
        guard.__exit__(*sys.exc_info())
        raise


def worker(args):
    guard = None
    try:
        protocol, anchor = verified_protocol(args) if args.protocol else (None, None)
        if protocol:
            if type(args.slot) is not int or not 0 <= args.slot < len(protocol["schedule"]):
                raise ValueError("Official worker requires a planned slot index")
            row = protocol["schedule"][args.slot]
            ceilings = protocol["ceilings"]
            for supplied, key in ((args.max_requests, "max_requests"), (args.timeout, "hard_slot_timeout_seconds"),
                                  (args.request_timeout, "request_timeout_seconds")):
                if supplied != ceilings[key]:
                    raise ValueError("Official worker ceiling differs from its pinned protocol")
        else:
            if str(args.task_id) not in EXCLUDED or args.arm not in {"native", "G"}:
                raise ValueError("Development native tasks are restricted to excluded IDs19/20")
            reservation = load_json(args.development_reservation)
            if (sha_file(args.development_reservation) != args.development_reservation_sha256
                    or reservation["category"] != "excluded_native"
                    or reservation["task_id"] != args.task_id or reservation["arm"] != args.arm
                    or reservation["reserved_maximum_requests"] != args.max_requests
                    or Path(reservation["output"]).resolve() / "episode" != Path(args.output).resolve()
                    or reservation["source_files"] != actual_source_files()):
                raise ValueError("Development worker differs from its pre-request reservation")
            row = {"task_id": args.task_id, "arm": args.arm, "seed": 1701,
                   "episode_id": "development-" + str(args.task_id) + "-" + args.arm}
            ceilings = {"max_requests": args.max_requests, "max_steps": 80,
                        "hard_slot_timeout_seconds": args.timeout, "request_timeout_seconds": args.request_timeout}
        guard, gate, identity = runtime_gate(args, protocol)
        from research.native_agent.harness import run_episode
        status = run_episode(native_root=args.native_root, output=args.output,
            task_id=row["task_id"], arm=row["arm"], episode_id=row["episode_id"], seed=row["seed"],
            guard=guard, context_gate=gate, max_requests=ceilings["max_requests"], max_steps=ceilings["max_steps"],
            timeout_seconds=ceilings["hard_slot_timeout_seconds"],
            request_timeout_seconds=ceilings["request_timeout_seconds"])
        write_new(Path(args.output) / "worker-identity.json", identity)
        if status != "native_returned" and load_json(Path(args.output) / "execution-receipt.json")["stage"] == "startup":
            raise ValueError("Native harness refused startup; see retained execution-error.json")
        if protocol:
            verify_files(ROOT, protocol["source"]["files"])
            verify_native_binding(args.native_root, protocol["native"])
            write_new(Path(args.output) / "protocol-anchor.json", anchor)
        return 0 if status == "native_returned" else 1
    except BaseException as exc:
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        write_new(output / "startup-fatal.json", {"schema": "conseqax-native-integrity-failure-v1",
            "recorded_utc": utc(), "error_type": type(exc).__name__, "message": str(exc),
            "traceback": traceback.format_exc(), "integrity_exit_code": INTEGRITY_EXIT,
            "semantic_reward_not_fabricated": True})
        return INTEGRITY_EXIT
    finally:
        if guard:
            guard.__exit__(None, None, None)


def transport_smoke(args):
    reservation = reserve_development(args, "task_independent_transport", 2)
    output = Path(args.output)
    output.mkdir(exist_ok=False, parents=True)
    guard, gate, identity, context_journal = None, None, None, None
    result = {"started_utc": utc(), "official_tasks_read": 0, "generation_attempts": 0,
              "purpose": "task-independent structured-call and tool-result roundtrip", "passed": False,
              "development_reservation": str(reservation), "development_reservation_sha256": sha_file(reservation),
              "source_files": actual_source_files()}
    try:
        from research.native_agent.harness import Journal

        context_journal = Journal(output / "context-events.jsonl")
        guard, gate, identity = runtime_gate(args)
        gate.on_receipt = lambda receipt: context_journal.append({"kind": "context_gate_result", "receipt": receipt})
        import httpx
        payload = load_json(args.wire)["observed"]["body"]
        payload.update(seed=1701, temperature=0, max_tokens=128, stream=False)
        payload["messages"][1]["content"] = (
            "Transport compatibility fixture: call get_reservation_details with reservation_id "
            "NATIVE_TRANSPORT_FIXTURE. This is a synthetic tool transport check.")
        payload["tool_choice"] = {"type": "function", "function": {"name": "get_reservation_details"}}
        responses = []
        with httpx.Client(trust_env=False, timeout=args.request_timeout) as client:
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
        result.update(passed=bool(responses[1]["choices"][0]["message"].get("content")))
    except BaseException as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        result["context_checks"] = gate.receipts if gate else []
        result["identity"] = identity
        if guard:
            result["network_events"] = guard.events
            guard.__exit__(None, None, None)
        if context_journal:
            context_journal.close()
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
        "--max-requests", str(maximum if maximum is not None else args.max_requests),
        "--request-timeout", str(args.request_timeout)]
    if protocol:
        command += ["--protocol", args.protocol, "--slot", str(slot),
                    "--protocol-sha256", canonical_sha(protocol), "--protocol-commit", args.protocol_commit]
    else:
        command += ["--task-id", str(args.task_id), "--arm", args.arm,
                    "--development-reservation", args.development_reservation,
                    "--development-reservation-sha256", args.development_reservation_sha256]
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
    process, code, timed_out, supervisor_error, cleanup_errors = None, None, False, None, []
    try:
        with (output / "stdout.log").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(command, env=environment, cwd=ROOT, stdout=stdout, stderr=stderr,
                                       startupinfo=startup, creationflags=flags)
            write_new(output / "parent-start.json", {"started_utc": utc(), "pid": process.pid,
                "command": command, "hard_deadline_seconds": args.timeout, "corrective_reruns": 0})
            try:
                code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
    except BaseException as exc:
        supervisor_error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                code = process.wait(timeout=30)
            except BaseException as exc:
                cleanup_errors.append({"type": type(exc).__name__, "message": str(exc)})
        if supervisor_error or cleanup_errors:
            code = 70
        elif timed_out:
            code = 124
        write_new(output / "parent-receipt.json", {"finished_utc": utc(), "exit_code": code,
            "child_return_code": process.returncode if process is not None else None,
            "hard_timeout": timed_out, "wall_seconds": time.monotonic() - start,
            "saved_simulation_available": (episode / "native-simulation.json").is_file(),
            "supervisor_error": supervisor_error, "cleanup_errors": cleanup_errors,
            "partial_artifacts_preserved": True})
    return code


def bind_evidence(path):
    path = Path(path).resolve()
    if path.is_file():
        return {"path": str(path), "kind": "file", "sha256": sha_file(path)}
    if not path.is_dir():
        raise ValueError("Required readiness evidence is absent")
    return {"path": str(path), "kind": "directory", "files": {
        item.relative_to(path).as_posix(): {"sha256": sha_file(item), "bytes": item.stat().st_size}
        for item in sorted(path.rglob("*")) if item.is_file()}}


def verify_evidence(record):
    if record["kind"] == "file":
        if sha_file(record["path"]) != record["sha256"]:
            raise ValueError("Bound readiness file changed")
    elif record["kind"] == "directory":
        directory = Path(record["path"])
        if {item.relative_to(directory).as_posix() for item in directory.rglob("*") if item.is_file()} != set(record["files"]):
            raise ValueError("Readiness directory inventory changed")
        verify_files(directory, record["files"])
    else:
        raise ValueError("Unknown readiness evidence type")


def context_evidence_passed(checks, expected):
    return (len(checks) == expected and all(check.get("passed") is True and check.get("same_rendered_bytes") is True
            and check.get("same_token_ids") is True for check in checks))


def inspect_readiness_inputs(args):
    source = actual_source_files()
    transport_path = Path(args.transport_result)
    transport = load_json(transport_path)
    if (transport.get("passed") is not True or transport.get("generation_attempts") != 2
            or transport.get("official_tasks_read") != 0 or transport.get("source_files") != source
            or not context_evidence_passed(transport.get("context_checks", []), 2)):
        raise ValueError("Transport readiness requires two retained exact-source, exact-render successful calls")
    transport_root = transport_path.parent
    for index in (0, 1):
        response = load_json(transport_root / f"response-{index}.json")
        if not response.get("choices"):
            raise ValueError("Transport response is absent")
    evidence = {"transport": bind_evidence(transport_root)}
    for label, slot_path, arm, task_id in (("native", args.native_episode, "native", "19"),
                                           ("guarded", args.guarded_episode, "G", "20")):
        slot = Path(slot_path)
        episode = slot / "episode"
        parent, execution = load_json(slot / "parent-receipt.json"), load_json(episode / "execution-receipt.json")
        identity = load_json(episode / "worker-identity.json")
        simulation = load_json(episode / "native-simulation.json")
        configuration = load_json(episode / "configuration.json")
        if (parent.get("exit_code") != 0 or parent.get("hard_timeout") or parent.get("supervisor_error")
                or execution.get("status") != "native_returned" or execution.get("capture_errors")
                or execution.get("arm") != arm or execution.get("task_id") != task_id
                or identity.get("source_files") != source or simulation.get("reward_info") is None
                or configuration.get("required_reward_basis") != ["DB", "COMMUNICATE"]):
            raise ValueError("Native readiness requires retained exact-source native grading, regardless of task reward")
        for key in ("version", "tag", "launch_receipt_sha256", "server_executable_sha256",
                    "model_blob_sha256", "runner_configuration", "runner_binding", "server_create_time", "runner_create_time"):
            if identity.get(key) != transport["identity"].get(key):
                raise ValueError("Readiness smoke runtime identities/configurations differ")
        attempted = execution["model_requests"]["attempted"]
        checks = load_json(episode / "context-checks.json")["checks"]
        if attempted < 2 or not context_evidence_passed(checks, attempted):
            raise ValueError("Native user/assistant model integration was not established")
        if label == "guarded":
            events = [json.loads(line) for line in (episode / "controller-events.jsonl").read_text().splitlines()]
            if not any(event.get("event") == "receipt"
                       and event.get("receipt", {}).get("framework_version") == "2.1.1" for event in events):
                raise ValueError("Guarded native smoke did not exercise a real current-field receipt")
        evidence[label] = bind_evidence(slot)
    return source, evidence


def readiness(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    source, evidence = inspect_readiness_inputs(args)
    write_new(output / "readiness.json", {"schema": "conseqax-native-readiness-v1", "passed": True,
        "recorded_utc": utc(), "source_files": source, "evidence": evidence,
        "server_launch": {"path": str(Path(args.server_launch).resolve()), "sha256": sha_file(args.server_launch)},
        "runtime": runtime_binding(args.wheel), "task_reward_one_required": False,
        "meaning": "Execution, structured tool transport, native grading and guarded receipt integration; not task-outcome selection"})
    return 0


def verify_readiness(path, args):
    receipt = load_json(path)
    if (receipt.get("schema") != "conseqax-native-readiness-v1" or receipt.get("passed") is not True
            or receipt.get("source_files") != actual_source_files()
            or receipt.get("runtime") != runtime_binding(args.wheel)
            or receipt.get("task_reward_one_required") is not False
            or set(receipt.get("evidence", {})) != {"transport", "native", "guarded"}
            or Path(receipt["server_launch"]["path"]).resolve() != Path(args.server_launch).resolve()
            or sha_file(args.server_launch) != receipt["server_launch"]["sha256"]):
        raise ValueError("Readiness is not bound to the exact frozen execution source/runtime/configuration")
    for evidence in receipt["evidence"].values():
        verify_evidence(evidence)
    from types import SimpleNamespace

    evidence_args = SimpleNamespace(
        transport_result=str(Path(receipt["evidence"]["transport"]["path"]) / "transport-smoke-result.json"),
        native_episode=receipt["evidence"]["native"]["path"],
        guarded_episode=receipt["evidence"]["guarded"]["path"])
    source, evidence = inspect_readiness_inputs(evidence_args)
    if source != receipt["source_files"] or evidence != receipt["evidence"]:
        raise ValueError("Raw readiness smoke evidence does not support its receipt")
    return receipt


def freeze(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    source = source_binding(ROOT)
    native = native_binding(args.native_root)
    metadata = select_metadata(load_json(Path(args.native_root) / "data/tau2/domains/airline/tasks.json"))
    verify_readiness(args.readiness, args)
    guard, _, identity = runtime_gate(args)
    guard.__exit__(None, None, None)
    protocol = {"schema": "conseqax-native-prospective-protocol-v1", "frozen_utc": utc(),
        "source": source, "native_root": str(Path(args.native_root).resolve()), "native": native,
        "runtime": runtime_binding(args.wheel), "runtime_identity": identity,
        "selection": metadata, "schedule": make_schedule(metadata),
        "model": {"tag_digest": MODEL_DIGEST, "api_base": RESEARCH_API_BASE, "context_tokens": 16384,
            "kv_cache": "q8_0", "flash_attention": True, "temperature": 0, "seed": 1701,
            "max_output_tokens": 512, "cache_capacity_slots": identity["runner_configuration"]["cache_capacity_slots"],
            "simultaneous_generation_clients": 1, "render_tokenizer_gate": "every actual request, no truncation"},
        "ceilings": {"max_steps": 80, "max_consecutive_errors": 5, "max_requests": 48,
                     "request_timeout_seconds": args.request_timeout, "hard_slot_timeout_seconds": args.timeout,
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
    protocol, anchor = verified_protocol(args)
    ceilings = protocol["ceilings"]
    args.timeout, args.max_requests = ceilings["hard_slot_timeout_seconds"], ceilings["max_requests"]
    args.request_timeout = ceilings["request_timeout_seconds"]
    if source_binding(ROOT) != protocol["source"] or runtime_binding(args.wheel) != protocol["runtime"]:
        raise ValueError("Prospective source/runtime changed")
    verify_native_binding(args.native_root, protocol["native"])
    verify_readiness(protocol["readiness_receipt"]["path"], args)
    guard, _, _ = runtime_gate(args, protocol)
    guard.__exit__(None, None, None)
    write_new(Path(args.protocol).parent / "exclusive-collection-claim.json",
              {"claimed_utc": utc(), **anchor, "output": args.output})
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=False)
    dispositions = [{**row, "status": "unstarted", "reason": "Collection has not reached this slot"}
                    for row in protocol["schedule"]]
    stopped, collection_error = None, None
    original_output = args.output
    try:
        for row in protocol["schedule"]:
            index = row["slot"]
            if stopped:
                dispositions[index] = {**row, "status": "unstarted", "reason": stopped}
                continue
            try:
                verify_files(ROOT, protocol["source"]["files"])
                verify_native_binding(args.native_root, protocol["native"])
            except BaseException as exc:
                stopped = f"Integrity stop before slot: {type(exc).__name__}: {exc}"
                dispositions[index] = {**row, "status": "unstarted", "reason": stopped}
                continue
            args.output = str(destination / f"slot-{index:03d}-{row['task_id']}-{row['arm']}")
            try:
                code = supervise(args, slot=index, protocol=protocol)
            except BaseException as exc:
                code = 70
                collection_error = {"type": type(exc).__name__, "message": str(exc),
                                    "traceback": traceback.format_exc()}
            disposition = "worker_returned" if code == 0 else "execution_failed"
            if code == INTEGRITY_EXIT:
                disposition, stopped = "integrity_failed", "Worker startup/runtime/source integrity failure"
            elif code == 70:
                disposition, stopped = "supervisor_failed", "Parent supervision or child cleanup failure"
            dispositions[index] = {**row, "status": disposition, "exit_code": code}
            write_new(destination / f"disposition-{index:03d}.json", dispositions[index])
            print(json.dumps(dispositions[index]), flush=True)
    except BaseException as exc:
        stopped = f"Collection parent interrupted: {type(exc).__name__}: {exc}"
        collection_error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        args.output = original_output
        for index, disposition in enumerate(dispositions):
            if disposition["status"] == "unstarted":
                disposition["reason"] = stopped or "Collection ended before slot startup"
            path = destination / f"disposition-{index:03d}.json"
            if not path.exists():
                write_new(path, disposition)
        write_new(destination / "collection-receipt.json", {**anchor,
            "finished_utc": utc(), "all_planned_slots": dispositions, "integrity_stop": stopped,
            "collection_error": collection_error, "corrective_reruns": 0,
            "complete_planned_matrix": len(dispositions) == len(protocol["schedule"]) == 48})
        from research.native_agent.harness import seal_directory
        seal_directory(destination, "conseqax-native-collection-v1")
    return 0 if not stopped else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("transport-smoke", "development", "worker", "readiness", "freeze", "collect"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--native-root", required=True)
    parser.add_argument("--models", default="C:/Users/DELL/.ollama/models")
    parser.add_argument("--wheel", required=True)
    parser.add_argument("--server-launch", required=True)
    parser.add_argument("--wire")
    parser.add_argument("--readiness")
    parser.add_argument("--transport-result")
    parser.add_argument("--native-episode")
    parser.add_argument("--guarded-episode")
    parser.add_argument("--protocol")
    parser.add_argument("--protocol-commit")
    parser.add_argument("--protocol-sha256")
    parser.add_argument("--task-id")
    parser.add_argument("--arm", default="native")
    parser.add_argument("--slot", type=int)
    parser.add_argument("--max-requests", type=int, default=48)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--request-timeout", type=int, default=600)
    parser.add_argument("--development-ledger", default=str(ROOT / "output/native-development-2026-10-21"))
    parser.add_argument("--development-reservation")
    parser.add_argument("--development-reservation-sha256")
    args = parser.parse_args()
    if args.phase == "worker":
        return worker(args)
    if args.phase == "transport-smoke":
        return transport_smoke(args)
    if args.phase == "development":
        if str(args.task_id) not in EXCLUDED or args.arm not in {"native", "G"}:
            parser.error("Only excluded native tasks19/20 and native/G development arms are permitted")
        reservation = reserve_development(args, "excluded_native", args.max_requests)
        args.development_reservation = str(reservation)
        args.development_reservation_sha256 = sha_file(reservation)
        code = supervise(args)
        settle_development(reservation, args.output)
        return code
    if args.phase == "readiness":
        return readiness(args)
    if args.phase == "freeze":
        return freeze(args)
    if args.phase == "collect":
        return collect(args)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
