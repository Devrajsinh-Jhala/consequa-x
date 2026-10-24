"""Independent offline native replay: no collector, policy, transport or SDK import.

Every saved model input is reproduced by unchanged native orchestration. Saved
raw responses are parsed by the pinned native client, never by a live model.
The package arm is independently replayed with the original native guard: this
tests its declared behavioral conformance, including public verification work,
actual tool effects and final late settling. No receipt superiority is assumed.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
import hashlib
import inspect
import json
from pathlib import Path
import socket
import sys

from .protocol import ARMS, canonical, file_binding, utc, verify_files, verify_protocol, write_new


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same(left, right, message):
    require(canonical(left) == canonical(right), message)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def jsonl(path):
    data = Path(path).read_bytes()
    require(not data or data.endswith(b"\n"), "Journal has an incomplete trailing record")
    return [json.loads(line) for line in data.splitlines()]


@contextmanager
def no_network():
    original_connect, original_create = socket.socket.connect, socket.create_connection
    def refuse(*args, **kwargs):
        raise RuntimeError("Network is forbidden in independent offline audit")
    socket.socket.connect = refuse
    socket.create_connection = refuse
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection = original_connect, original_create


def serial(value):
    """Independent deterministic trusted-state serialization."""
    if is_dataclass(value):
        return serial(asdict(value))
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    if isinstance(value, set):
        return sorted(serial(v) for v in value)
    if isinstance(value, dict):
        if all(type(k) is str for k in value):
            return {k: serial(v) for k, v in value.items()}
        return {"__mapping_pairs__": sorted([[serial(k), serial(v)] for k, v in value.items()],
                                           key=lambda pair: canonical(pair[0]))}
    raise TypeError("Unexpected replay state type")


def snapshot(world):
    result = {k: v for k, v in vars(world).items() if k not in ("rng", "deferred")}
    result["rng_state"] = world.rng.getstate()
    result["deferred"] = [[due, sequence, metadata]
                          for due, sequence, _callback, metadata in world.deferred]
    return serial(result)


@contextmanager
def replay_instrumentation(work_limits=None):
    from limbo.runtime import ToolRuntime
    from limbo.world import World
    old_init, old_advance = ToolRuntime.__init__, World.advance
    old = {name: getattr(ToolRuntime, name) for name in ("execute", "verify", "flush")}
    work_limits = work_limits or {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800}
    state = {"rt": None, "initial": None, "stack": [], "events": [], "next": 0,
             "counts": {"execute": 0, "verify": 0, "advance": 0}, "wait_seconds": 0.0}
    def initialize(rt, *args, **kwargs):
        old_init(rt, *args, **kwargs)
        require(state["rt"] is None, "Multiple native runtime instances during replay")
        state["rt"], state["initial"] = rt, snapshot(rt.world)
    def wrapper(op, original):
        def call(obj, *args, **kwargs):
            rt = state["rt"]
            if rt is None or (op == "advance" and obj is not rt.world):
                return original(obj, *args, **kwargs)
            require(op != "verify" or kwargs.get("truth", False) is False,
                    "Privileged read in offline replay")
            ident = state["next"]
            state["next"] += 1
            bound = inspect.signature(original).bind(obj, *args, **kwargs)
            bound.apply_defaults()
            fields = bound.arguments
            positionals = ([fields["name"], fields["args"]] if op == "execute" else
                           [fields["name"], fields["args"], fields["t_call"]] if op == "verify" else
                           [fields["seconds"]] if op == "advance" else [])
            keywords = ({"source": fields["source"], "note": fields["note"]} if op == "execute" else
                        {"truth": fields["truth"]} if op == "verify" else {})
            state["events"].append({"event": "enter", "id": ident,
                "parent": state["stack"][-1] if state["stack"] else None,
                "op": op, "args": serial(positionals), "kwargs": serial(keywords), "clock": rt.world.clock})
            state["stack"].append(ident)
            try:
                if op in ("execute", "verify"):
                    state["counts"][op] += 1
                    if state["counts"][op] > work_limits[op]:
                        raise RuntimeError("Uniform native " + op + " budget exhausted")
                if op == "advance" and state["events"][-1]["parent"] is None:
                    state["counts"]["advance"] += 1
                    state["wait_seconds"] += float(args[0] if args else kwargs["seconds"])
                    if state["counts"]["advance"] > work_limits["wait"] or state["wait_seconds"] > work_limits["total_wait_seconds"]:
                        raise RuntimeError("Uniform native wait budget exhausted")
                result = original(obj, *args, **kwargs)
            except BaseException as exc:
                state["events"].append({"event": "raise", "id": ident,
                    "type": type(exc).__name__, "message": str(exc), "clock": rt.world.clock})
                raise
            else:
                state["events"].append({"event": "return", "id": ident,
                                       "result": serial(result), "clock": rt.world.clock})
                return result
            finally:
                state["stack"].pop()
        return call
    ToolRuntime.__init__ = initialize
    for name, original in old.items():
        setattr(ToolRuntime, name, wrapper(name, original))
    World.advance = wrapper("advance", old_advance)
    try:
        yield state
    finally:
        ToolRuntime.__init__, World.advance = old_init, old_advance
        for name, original in old.items():
            setattr(ToolRuntime, name, original)


def verify_manifest(directory):
    directory = Path(directory).resolve()
    expected = load(directory / "manifest.json")
    actual_names = {str(p.relative_to(directory)).replace("\\", "/")
                    for p in directory.rglob("*") if p.is_file() and p != directory / "manifest.json"}
    require(set(expected) == actual_names, "Artifact manifest inventory differs")
    verify_files(directory, expected)
    return expected


def audit_model_call(directory, number, native_input, protocol):
    """Reconstruct exact native request independently with a non-network _post."""
    from limbo.llm import LLMClient
    prefix = Path(directory) / f"{number:04d}"
    terminal = load(str(prefix) + "-terminal.json")
    same(load(str(prefix) + "-native-input.json"), native_input, "Native input/history/schema was altered")
    require(terminal["invocation"] == number and terminal["dispatches"] in (0, 1),
            "Invalid single-dispatch terminal")
    captured = []
    class CaptureStop(BaseException):
        pass
    class OfflineNativeClient:
        model = protocol["runtime_binding"]["model"]
        max_output_tokens = protocol["limits"]["max_output_tokens"]
        temperature = 0
        def _post(self, path, body):
            require(path == "/chat/completions", "Native request path changed")
            captured.append(body)
            raise CaptureStop()
    try:
        LLMClient._complete_chat(OfflineNativeClient(), native_input["system"],
                                 native_input["conversation"], native_input["tools"])
    except CaptureStop:
        pass
    expected = {**captured[0], "seed": protocol["seed"]}
    wire_path = Path(str(prefix) + "-request.bin")
    if wire_path.exists():
        wire = wire_path.read_bytes()
        request = json.loads(wire)
        same(request, expected, "Native message/schema serialization was changed")
        require(wire == json.dumps(expected, allow_nan=False).encode("utf-8"),
                "Actual wire bytes differ from exact declared native serializer")
    if terminal["dispatches"]:
        require(wire_path.exists(), "Dispatch lacks bound request bytes")
        gate = load(str(prefix) + "-context.json")
        same(gate["request"], expected, "Context proof is not bound to actual wire payload")
        require(gate.get("passed") is True and gate.get("same_rendered_bytes") is True
                and gate.get("same_token_ids") is True, "Context parity proof failed")
        same(gate["runtime_binding"], protocol["runtime_binding"], "Runtime binding changed")
        prompt = gate["offline_rendered_prompt"]
        same(prompt, gate["server_preview"]["_debug_info"]["rendered_template"], "Saved render bytes differ")
        tokens = gate["runtime_tokenizer"]["tokens"]
        context = gate["offline_context"]
        require(context["prompt_tokens"] == len(tokens)
                and context["rendered_prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
                and context["required_tokens"] == len(tokens) + protocol["limits"]["max_output_tokens"] + 64
                and context["context_tokens"] == protocol["runtime_binding"]["context_tokens"]
                and context["fits"] is True and context["truncation_requested"] is False,
                "Context token budget is inconsistent")
    raw_path = Path(str(prefix) + "-response.bin")
    if not raw_path.exists():
        require(terminal["returned"] is False, "Returned model invocation lacks raw response")
        return None, terminal
    raw = raw_path.read_bytes()
    response_meta = load(str(prefix) + "-response-meta.json")
    require(response_meta["body_sha256"] == hashlib.sha256(raw).hexdigest(), "Raw response hash differs")
    if response_meta["status"] != 200:
        require(not terminal["returned"], "Non-200 model response counted as completion")
        return None, terminal
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        require(not terminal["returned"], "Malformed raw JSON was counted as a completion")
        require(terminal["usage"] is None, "Malformed JSON cannot establish metered usage")
        return None, terminal
    if not isinstance(payload, dict):
        require(not terminal["returned"], "Non-object response counted as completion")
        return None, terminal
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    completion_details = usage.get("completion_tokens_details")
    completion_details = completion_details if isinstance(completion_details, dict) else {}
    actual = {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
              "cached_tokens": details.get("cached_tokens"),
              "reasoning_tokens": usage.get("reasoning_tokens", completion_details.get("reasoning_tokens"))}
    for name, value in actual.items():
        valid = type(value) is int and value >= 0
        same(terminal["usage"][name], {"available": valid, "value": value if valid else None},
             "Missing usage was replaced by zero or usage differs")
    if not terminal["returned"]:
        return None, terminal
    require(terminal["dispatches"] == 1, "Returned model invocation lacks exactly one dispatch")
    class ResponseClient(OfflineNativeClient):
        def _post(self, path, body):
            return payload, 0.0
    parsed = LLMClient._complete_chat(ResponseClient(), native_input["system"],
                                    native_input["conversation"], native_input["tools"])
    return parsed, terminal


def audit_episode(directory, slot, protocol):
    from limbo import agent
    from limbo.policies import make_policy as native_policy
    from limbo.llm import LLMError
    directory = Path(directory)
    inventory = verify_manifest(directory)
    parent = load(directory / "parent-terminal.json")
    base = {"slot": slot["slot"], "world_rank": slot["world_rank"], "arm": slot["arm"],
            "started": True, "operational": False, "grade_available": False,
            "execution_success": False, "native_grade": None, "audit_complete": False}
    if parent["status"] != "child_returned" or parent["exit_code"] != 0:
        base.update(status=parent["status"], unavailable_reason="Native terminal not available",
                    observed_journal_prefix=partial_counts(directory), inventory_files=len(inventory))
        return base
    terminal = load(directory / "worker-terminal.json")
    if terminal["status"] != "native_returned":
        base.update(status="worker_failed", unavailable_reason="Worker did not return native result")
        return base
    saved = load(directory / "native-result.json")
    same(saved["spec"], slot["spec"], "Episode specification differs from frozen slot")
    model_dir = directory / "model"
    terminals = sorted(model_dir.glob("*-terminal.json"))
    require(len(terminals) <= protocol["limits"]["max_requests"] + 1, "Model budget exceeded")
    call_records = jsonl(model_dir / "model-calls.jsonl")
    returns = sum(row["event"] == "request_return" for row in call_records)
    dispatches = [row for row in call_records if row["event"] == "before_dispatch"]
    require(all(row["dispatches"] == 1 for row in dispatches), "Multiple generation sends")
    require(len(dispatches) <= protocol["limits"]["max_requests"], "Actual dispatch allowance exceeded")
    replay_terminals = []
    class ReplayClient:
        protocol = "chat"
        def complete(self, system, conversation, tools):
            number = len(replay_terminals) + 1
            turn, item = audit_model_call(model_dir, number,
                {"system": system, "conversation": conversation, "tools": tools}, protocol)
            replay_terminals.append(item)
            if turn is None:
                require(saved["stop_reason"] == "llm_error" and saved["error"].startswith("LLMError: "),
                        "Failed model dispatch lacks native failure disposition")
                raise LLMError(saved["error"][len("LLMError: "):], retryable=False)
            return turn
    original_factory = agent.make_policy
    agent.make_policy = lambda name, ident: native_policy("guard" if name == "conseqax_guard" else name, ident)
    try:
        with replay_instrumentation(protocol["limits"]["work"]) as observed:
            replay = agent.run_episode(agent.EpisodeSpec(**slot["spec"]), client=ReplayClient())
            same(jsonl(directory / "runtime.jsonl"),
                 observed["events"], "Actual execute/verify/wait/flush replay differs")
            same(load(directory / "world.json"),
                 {"initial": observed["initial"], "final": snapshot(observed["rt"].world)},
                 "Initial/final native world or ledger differs")
    finally:
        agent.make_policy = original_factory
    require(len(replay_terminals) == len(terminals), "Unused or missing model invocation artifact")
    validate_model_journal(call_records, replay_terminals, protocol["limits"]["max_requests"])
    if len(terminals) > protocol["limits"]["max_requests"]:
        final = replay_terminals[-1]
        require(final["dispatches"] == 0 and final["returned"] is False
                and final.get("error", {}).get("message") == "Declared combined model-invocation cap exhausted",
                "Extra invocation is not an explicit final pre-dispatch cap refusal")
    require(returns == sum(item["returned"] for item in replay_terminals), "Return journal accounting mismatch")
    # Wall execution/inference latency is descriptive and cannot be reproduced
    # by cached responses. Every scientific native field must match exactly.
    for name in ("wall_s", "llm_latency_s"):
        replay.pop(name, None)
    comparable = {k: v for k, v in saved.items() if k not in ("wall_s", "llm_latency_s")}
    same(replay, comparable, "Native orchestration, policy, grading or conversation replay differs")
    events = observed["events"]
    counts = Counter(row["op"] for row in events if row["event"] == "enter")
    receipts = [row for row in jsonl(directory / "framework.jsonl") if row.get("operation") == "package_receipt"]
    if slot["arm"] != "conseqax_guard":
        require(not receipts, "SDK receipt appeared in an unmodified native comparator")
    else:
        require(len(receipts) == counts["verify"], "SDK receipt count differs from actual public verifications")
        audit_receipts(receipts, events, saved["episode_id"])
    usage = {}
    for name in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"):
        values = [(item.get("usage") or {}).get(name, {}).get("value") for item in replay_terminals]
        usage[name] = {"observed_prefix_total": sum(v for v in values if v is not None),
                       "unknown_invocations": sum(v is None for v in values),
                       "complete_for_all_invocations": all(v is not None for v in values)}
    execution_success = saved["error"] is None and saved["stop_reason"] not in ("llm_error", "harness_error")
    base.update(status="audited_native_return" if execution_success else "audited_native_error_return",
                operational=True, grade_available=True, execution_success=execution_success, audit_complete=True,
                native_grade=saved["grade"], native_stop_reason=saved["stop_reason"],
                native_error=saved["error"], fault_triggered=saved["fault_triggered"],
                work=dict(counts), model_invocations=len(terminals), model_completions=returns,
                model_dispatches=len(dispatches), usage=usage, receipt_count=len(receipts),
                model_cap_refusals=max(0, len(terminals) - protocol["limits"]["max_requests"]),
                work_charges={"native_tool_events": saved["n_executions"],
                              "public_verify_attempts": counts["verify"],
                              "outer_wait_attempts": sum(row["event"] == "enter" and row["op"] == "advance"
                                                         and row["parent"] is None for row in events),
                              "outer_virtual_wait_seconds": sum(row["args"][0] for row in events
                                  if row["event"] == "enter" and row["op"] == "advance" and row["parent"] is None),
                              "flush_attempts": counts["flush"],
                              "boundary_enter_counts_are_not_physical_effect_counts": True},
                package_same_native_guard_replay=slot["arm"] == "conseqax_guard",
                wall_s=saved["wall_s"], virtual_seconds=saved["virtual_seconds"])
    return base


def validate_model_journal(records, terminals, max_requests):
    """A serial invocation has one start, at most one dispatch, one terminal."""
    relevant = [r for r in records if r.get("event") != "client_ready"]
    position = 0
    for number, terminal in enumerate(terminals, 1):
        require(position < len(relevant), "Invocation journal is missing its start")
        start = relevant[position]
        require(start.get("event") == "request_start" and start.get("invocation") == number,
                "Invocation starts are missing, duplicated or out of serial order")
        position += 1
        dispatched = False
        if position < len(relevant) and relevant[position].get("event") == "before_dispatch":
            require(relevant[position].get("invocation") == number
                    and relevant[position].get("dispatches") == 1, "Dispatch identity differs")
            dispatched = True
            position += 1
        require(position < len(relevant), "Invocation journal lacks terminal")
        ending = relevant[position]
        expected = "request_return" if terminal["returned"] else "request_error"
        require(ending.get("event") == expected and ending.get("invocation") == number,
                "Invocation terminal is duplicated, missing or out of order")
        require(terminal["dispatches"] == int(dispatched), "Journal and terminal dispatch count differ")
        if number > max_requests:
            require(not dispatched and not terminal["returned"], "Cap-refused invocation dispatched")
        position += 1
    require(position == len(relevant), "Unattributed or duplicate model journal record")


def audit_receipts(receipts, events, episode_id):
    """Independently recompute the registered current-public-match predicate."""
    verifies = [event for event in events if event["event"] == "enter" and event["op"] == "verify"]
    endings = {event["id"]: event for event in events if event["event"] == "return"}
    require(len(receipts) == len(verifies), "Missing or extraneous receipt")
    for sequence, (row, call) in enumerate(zip(receipts, verifies), 1):
        require(row["phase"] == "return" and row["receipt_sequence"] == sequence, "Receipt sequence differs")
        receipt = row["receipt"]
        content = {k: v for k, v in receipt.items() if k != "content_sha256"}
        require(receipt["content_sha256"] == hashlib.sha256(canonical(content)).hexdigest(),
                "Receipt content hash differs")
        require(receipt["schema"] == "conseqax-limbo-public-verification-v1"
                and receipt["framework_version"] == "2.1.1", "Receipt framework/schema differs")
        name, args, t_call = call["args"]
        returned = endings[call["id"]]
        report = returned["result"]
        key = "limbo-public-" + hashlib.sha256(canonical(
            [episode_id, sequence, name, args, t_call, returned["clock"], report])).hexdigest()
        action, observation, verdict = (receipt[k] for k in ("action", "observation", "verification"))
        same(action["name"], name, "Receipt tool differs from actual public verification")
        same(action["arguments"], args, "Receipt arguments differ from actual public verification")
        same(observation["records"], [{"native": report}], "Receipt public report differs")
        require(action["action_id"] == key and action["contract"]["contract_id"] == key + ":current-visible-match"
                and action["contract"]["predicate"] == "limbo_current_public_verifier_match"
                and action["contract"]["deadline_ms"] == int(round(t_call * 1000))
                and action["contract"]["exact_count"] is None
                and action["registered_at_ms"] == int(round(t_call * 1000)), "Receipt action/contract binding differs")
        same(action["contract"]["expected"], {"tool": name, "arguments": args}, "Receipt expected predicate differs")
        require(observation["observation_id"] == key + ":public-report"
                and observation["source"] == "limbo_public_verifier"
                and observation["observed_at_ms"] == int(round(returned["clock"] * 1000))
                and observation["as_of_ms"] == observation["observed_at_ms"], "Receipt observation binding differs")
        status = {"found": "satisfied", "absent": "violated"}.get(report["status"], "unknown")
        require(verdict["status"] == status and verdict["origin"] == "unknown"
                and verdict["action_id"] == key and verdict["contract_id"] == action["contract"]["contract_id"]
                and verdict["observed_at_ms"] == observation["observed_at_ms"], "Receipt verdict differs")
        evidence = verdict["evidence"]
        require(len(evidence) == 1 and evidence[0]["details"]["native_status"] == report["status"]
                and evidence[0]["source"] == observation["source"]
                and evidence[0]["observation_id"] == observation["observation_id"]
                and evidence[0]["as_of_ms"] == observation["as_of_ms"], "Receipt evidence binding differs")


def partial_counts(directory):
    result = {"complete_accounting": False, "actual_work_may_exceed_valid_prefix": True}
    for filename in ("runtime.jsonl", "model/model-calls.jsonl"):
        path = Path(directory) / filename
        if not path.exists():
            result[filename] = {"available": False, "actual_count": None}
            continue
        valid = []
        trailing_invalid = False
        for line in path.read_bytes().splitlines():
            try:
                valid.append(json.loads(line))
            except (json.JSONDecodeError, UnicodeDecodeError):
                trailing_invalid = True
                break
        result[filename] = {"available": True, "valid_prefix_records": len(valid),
                            "trailing_invalid": trailing_invalid,
                            "counts": dict(Counter(row.get("event", "unknown") for row in valid))}
    return result


def summarize(rows):
    result = {}
    for arm in ARMS:
        chosen = [row for row in rows if row["arm"] == arm]
        result[arm] = {"planned": len(chosen), "started": sum(row["started"] for row in chosen),
            "audited_native_returns": sum(row["audit_complete"] for row in chosen),
            "operational": sum(row["operational"] for row in chosen),
            "unavailable_native_grade": sum(row["native_grade"] is None for row in chosen),
            "native_EOS_true_available": sum(bool((row["native_grade"] or {}).get("EOS")) for row in chosen),
            "operational_native_EOS": sum(row["operational"] and bool((row["native_grade"] or {}).get("EOS")) for row in chosen),
            "operational_native_TS": sum(row["operational"] and bool((row["native_grade"] or {}).get("TS")) for row in chosen)}
    return result


def audit_development(root, native_root, episode, output):
    """Same independent replay, explicitly excluded development data only."""
    episode, output = Path(episode).resolve(), Path(output).resolve()
    config = load(episode / "worker-config.json")
    protocol, slot = config["protocol"], config["slot"]
    require(slot["spec"]["index"] in (0, 1), "Development is confined to excluded indices zero/one")
    verify_files(root, protocol["sources"])
    verify_files(native_root, protocol["native"]["files"])
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(Path(native_root).resolve()))
    with no_network():
        row = audit_episode(episode, slot, protocol)
    verify_files(root, protocol["sources"])
    result = {"schema": "conseqax-limbo-development-audit-v1", "passed": row["audit_complete"],
              "utc": utc(), "sources": protocol["sources"], "native": protocol["native"],
              "spec": slot["spec"], "episode": str(episode), "episode_manifest": file_binding(episode / "manifest.json"),
              "row": row, "scope": "Excluded development; never an official benchmark score"}
    write_new(output / "audit-result.json", result)
    write_new(output / "manifest.json", {"audit-result.json": file_binding(output / "audit-result.json")})
    return result


def audit_collection(root, native_root, protocol_path, protocol_commit, collection, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before = file_binding(Path(collection) / "manifest.json")
    protocol = verify_protocol(root, native_root, protocol_path, protocol_commit)
    verify_manifest(collection)
    same(load(Path(collection) / "protocol.json"), protocol, "Collection protocol differs")
    record = load(Path(collection) / "collection.json")
    same(record["protocol_commit"], protocol_commit, "Collection protocol commit differs")
    require(len(record["rows"]) == len(protocol["schedule"]), "Planned slots were omitted")
    sys.path.insert(0, str(Path(native_root).resolve()))
    rows = []
    with no_network():
        for planned, disposition in zip(protocol["schedule"], record["rows"]):
            same([disposition[k] for k in ("slot", "world_rank", "arm")],
                 [planned[k] for k in ("slot", "world_rank", "arm")], "Slot identity/order mismatch")
            if disposition["status"].startswith("unstarted"):
                rows.append({"slot": planned["slot"], "world_rank": planned["world_rank"],
                    "arm": planned["arm"], "started": False, "operational": False,
                    "grade_available": False, "execution_success": False,
                    "native_grade": None, "audit_complete": False, "status": disposition["status"]})
            else:
                require(disposition["directory"] == f"slot-{planned['slot']:03d}", "Unsafe slot directory")
                rows.append(audit_episode(Path(collection) / disposition["directory"], planned, protocol))
    verify_manifest(collection)
    same(before, file_binding(Path(collection) / "manifest.json"), "Collection was changed during audit")
    result = {"schema": "conseqax-limbo-audit-v1", "passed": True, "utc": utc(),
              "protocol_commit": protocol_commit, "protocol": file_binding(protocol_path),
              "collection_manifest": before, "rows": rows, "summary": summarize(rows),
              "scope": {"independent_native_policy_and_effect_replay": True,
                        "conseqax_guard_replayed_as_declared_native_guard": True,
                        "SDK_receipt_current_public_report_mapping_recomputation": True,
                        "SDK_execution_or_independent_service_verifier_replay": False,
                        "saved_context_render_token_proof_consistency": True,
                        "independent_tokenizer_reconstruction": False,
                        "human_or_network_used": False,
                        "passed_means_all_slots_operational_or_successful": False}}
    write_new(output / "audit-result.json", result)
    write_new(output / "manifest.json", {"audit-result.json": file_binding(output / "audit-result.json")})
    return result
